# mono tray: служба трея (StatusNotifierWatcher + Host) для Hyprland без панели.
# Telegram, Discord, nm-applet и прочие регистрируют здесь свои значки;
# док показывает их внизу обзора по Super. Меню значков: com.canonical.dbusmenu.
import os

from gi.repository import GdkPixbuf, Gio, GLib

WATCHER_XML = """
<node>
  <interface name="{iface}">
    <method name="RegisterStatusNotifierItem"><arg type="s" direction="in"/></method>
    <method name="RegisterStatusNotifierHost"><arg type="s" direction="in"/></method>
    <property name="RegisteredStatusNotifierItems" type="as" access="read"/>
    <property name="IsStatusNotifierHostRegistered" type="b" access="read"/>
    <property name="ProtocolVersion" type="i" access="read"/>
    <signal name="StatusNotifierItemRegistered"><arg type="s"/></signal>
    <signal name="StatusNotifierItemUnregistered"><arg type="s"/></signal>
    <signal name="StatusNotifierHostRegistered"/>
  </interface>
</node>"""
IFACES = ("org.kde.StatusNotifierWatcher", "org.freedesktop.StatusNotifierWatcher")
ITEM_IFACES = ("org.kde.StatusNotifierItem", "org.freedesktop.StatusNotifierItem")


_icon_paths = {}  # имя значка -> путь (обход каталогов тем дорогой)


def find_icon(name, theme_path):
    key = (name, theme_path)
    if key not in _icon_paths:
        _icon_paths[key] = None
        for d in [theme_path, os.path.expanduser("~/.local/share/icons/hicolor"), "/usr/share/icons/hicolor",
                  "/usr/share/pixmaps", "/usr/share/icons/Adwaita"]:
            if not d or not os.path.isdir(d):
                continue
            best = None
            for root, _dirs, files in os.walk(d):
                for ext in (".svg", ".png"):
                    if name + ext in files:
                        p = os.path.join(root, name + ext)
                        if ext == ".svg" or best is None or "256" in root or "128" in root:
                            best = p
            if best:
                _icon_paths[key] = best
                break
    return _icon_paths[key]


class Item:
    def __init__(self, bus_name, path):
        self.bus_name, self.path = bus_name, path
        self.owner = bus_name if bus_name.startswith(":") else ""  # уникальное имя: от него идут сигналы
        self.iface = ITEM_IFACES[0]
        self.props = {}

    @property
    def key(self):
        return self.bus_name + self.path

    def get(self, name, default=None):
        return self.props.get(name, default)

    def title(self):
        tip = self.get("ToolTip")
        if tip and len(tip) > 2 and tip[2]:
            return tip[2]
        return self.get("Title") or self.get("Id") or ""

    def pixbuf(self, size):
        """картинка значка: из темы по IconName или из IconPixmap (ARGB, сетевой порядок байт)"""
        name = self.get("IconName") or ""
        theme_path = self.get("IconThemePath") or ""
        if name:
            if os.path.isabs(name) and os.path.exists(name):
                return GdkPixbuf.Pixbuf.new_from_file_at_size(name, size, size)
            p = find_icon(name, theme_path)
            if p:
                try:
                    return GdkPixbuf.Pixbuf.new_from_file_at_size(p, size, size)
                except GLib.Error:
                    pass
        pix = self.get("IconPixmap") or []
        if pix:
            w, h, data = max(pix, key=lambda p: p[0] * p[1])
            data = bytes(data)
            if w > 0 and h > 0 and len(data) >= w * h * 4:
                rgba = bytearray(len(data))
                rgba[0::4], rgba[1::4], rgba[2::4], rgba[3::4] = data[1::4], data[2::4], data[3::4], data[0::4]
                pb = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bytes(rgba)), GdkPixbuf.Colorspace.RGB,
                                                     True, 8, w, h, w * 4)
                return pb.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
        return None


class Tray:
    def __init__(self, on_change):
        self.on_change = on_change
        self.items = {}
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.reg_ids = []
        for iface in IFACES:
            node = Gio.DBusNodeInfo.new_for_xml(WATCHER_XML.format(iface=iface))
            self.reg_ids.append(self.bus.register_object(
                "/StatusNotifierWatcher", node.interfaces[0], self.on_call, self.on_get_prop, None))
            Gio.bus_own_name_on_connection(self.bus, iface, Gio.BusNameOwnerFlags.REPLACE, None, None)
        Gio.bus_own_name_on_connection(self.bus, f"org.kde.StatusNotifierHost-{os.getpid()}",
                                       Gio.BusNameOwnerFlags.NONE, None, None)
        self.bus.signal_subscribe("org.freedesktop.DBus", "org.freedesktop.DBus", "NameOwnerChanged",
                                  "/org/freedesktop/DBus", None, Gio.DBusSignalFlags.NONE, self.on_owner, None)
        self.bus.signal_subscribe(None, None, None, None, None, Gio.DBusSignalFlags.NONE, self.on_item_signal, None)

    # ---------- watcher
    def on_call(self, conn, sender, path, iface, method, params, inv):
        if method == "RegisterStatusNotifierItem":
            service = params.unpack()[0]
            if service.startswith("/"):
                bus_name, obj = sender, service
            else:
                bus_name, obj = service, "/StatusNotifierItem"
            self.add(bus_name, obj, iface)
            inv.return_value(None)
        elif method == "RegisterStatusNotifierHost":
            inv.return_value(None)
        else:
            inv.return_dbus_error("org.freedesktop.DBus.Error.UnknownMethod", method)

    def on_get_prop(self, conn, sender, path, iface, prop):
        if prop == "RegisteredStatusNotifierItems":
            return GLib.Variant("as", [i.bus_name + i.path for i in self.items.values()])
        if prop == "IsStatusNotifierHostRegistered":
            return GLib.Variant("b", True)
        if prop == "ProtocolVersion":
            return GLib.Variant("i", 0)
        return None

    def add(self, bus_name, path, watcher_iface):
        it = Item(bus_name, path)
        if watcher_iface.startswith("org.freedesktop"):
            it.iface = ITEM_IFACES[1]
        self.items[it.key] = it
        if not it.owner:
            def owner(conn, res):
                try:
                    it.owner = conn.call_finish(res).unpack()[0]
                except GLib.Error:
                    pass
            self.bus.call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "GetNameOwner",
                          GLib.Variant("(s)", (bus_name,)), GLib.VariantType("(s)"), Gio.DBusCallFlags.NONE, 2000,
                          None, owner)
        for iface in IFACES:
            self.bus.emit_signal(None, "/StatusNotifierWatcher", iface, "StatusNotifierItemRegistered",
                                 GLib.Variant("(s)", (it.key,)))
        self.refresh(it)

    def on_owner(self, conn, sender, path, iface, signal, params, _):
        name, old, new = params.unpack()
        if new:
            return
        gone = [k for k, it in self.items.items() if it.bus_name == name or (old and it.owner == old)]
        for k in gone:
            del self.items[k]
        if gone:
            self.on_change()

    def on_item_signal(self, conn, sender, path, iface, signal, params, _):
        if iface not in ITEM_IFACES or not signal.startswith("New"):
            return
        for it in self.items.values():
            if sender in (it.owner, it.bus_name) and it.path == path:
                self.refresh(it)

    def refresh(self, it):
        def done(conn, res):
            try:
                it.props = conn.call_finish(res).unpack()[0]
            except GLib.Error:
                if it.iface == ITEM_IFACES[0]:  # попробовать вариант freedesktop
                    it.iface = ITEM_IFACES[1]
                    self.refresh(it)
                return
            self.on_change()
        self.bus.call(it.bus_name, it.path, "org.freedesktop.DBus.Properties", "GetAll",
                      GLib.Variant("(s)", (it.iface,)), GLib.VariantType("(a{sv})"),
                      Gio.DBusCallFlags.NONE, 3000, None, done)

    # ---------- действия
    def visible(self):
        return [it for it in self.items.values() if it.props and it.get("Status") != "Passive"]

    def activate(self, it, x=0, y=0):
        method = "ContextMenu" if it.get("ItemIsMenu") else "Activate"
        self.bus.call(it.bus_name, it.path, it.iface, method, GLib.Variant("(ii)", (x, y)),
                      None, Gio.DBusCallFlags.NONE, 3000, None, None)

    def secondary(self, it):
        self.bus.call(it.bus_name, it.path, it.iface, "SecondaryActivate", GLib.Variant("(ii)", (0, 0)),
                      None, Gio.DBusCallFlags.NONE, 3000, None, None)

    def menu(self, it, done):
        """done(список пунктов) — пункты: dict(id, label, enabled, separator, toggle, checked, children)"""
        path = it.get("Menu")
        if not path:
            done([])
            return

        def parse(node):
            mid, props, children = node
            kids = [parse(c) for c in children]
            return {"id": mid, "label": (props.get("label") or "").replace("_", ""),
                    "enabled": props.get("enabled", True), "visible": props.get("visible", True),
                    "separator": props.get("type") == "separator",
                    "toggle": props.get("toggle-type", ""), "checked": props.get("toggle-state", 0) == 1,
                    "children": [k for k in kids if k["visible"]]}

        def got(conn, res):
            try:
                _rev, layout = conn.call_finish(res).unpack()
                done(parse(layout)["children"])
            except GLib.Error:
                done([])
        self.bus.call(it.bus_name, path, "com.canonical.dbusmenu", "AboutToShow", GLib.Variant("(i)", (0,)),
                      None, Gio.DBusCallFlags.NONE, 1000, None, None)
        self.bus.call(it.bus_name, path, "com.canonical.dbusmenu", "GetLayout",
                      GLib.Variant("(iias)", (0, -1, [])), GLib.VariantType("(u(ia{sv}av))"),
                      Gio.DBusCallFlags.NONE, 3000, None, got)

    def click(self, it, item_id):
        self.bus.call(it.bus_name, it.get("Menu"), "com.canonical.dbusmenu", "Event",
                      GLib.Variant("(isvu)", (item_id, "clicked", GLib.Variant("s", ""), 0)),
                      None, Gio.DBusCallFlags.NONE, 3000, None, None)
