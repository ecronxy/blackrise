#!/usr/bin/env python3
# mono-lock: экран блокировки blackrise в чёрно-белом ASCII-стиле.
# Настоящая блокировка Wayland (ext-session-lock): пока экран не разблокирован паролем,
# Hyprland не показывает ни одного окна. Пароль проверяет PAM (сервис swaylock, как у swaylock).
#   запускать через mono-lock: обёртка ждёт, пока экран реально заблокируется (как swaylock -f)
#   MONO_LOCK_TEST=5     проверка: сам разблокируется через 5 секунд
import os
import sys

RUN = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
PID = os.path.join(RUN, "mono-lock.pid")
READY = os.path.join(RUN, "mono-lock.ready")  # появляется, когда экран заблокирован

LIB = "/usr/lib64/libgtk4-layer-shell.so.0"
if os.path.exists(LIB) and LIB not in os.environ.get("LD_PRELOAD", ""):
    os.environ["LD_PRELOAD"] = (LIB + " " + os.environ.get("LD_PRELOAD", "")).strip()
    os.execv(sys.executable, [sys.executable] + sys.argv)
os.environ.pop("LD_PRELOAD", None)

import getpass  # noqa: E402
import json  # noqa: E402
import socket  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4SessionLock", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402
from gi.repository import Gtk4SessionLock as SL  # noqa: E402

import pam  # noqa: E402

HOME = os.path.expanduser("~")
USER = getpass.getuser()
HOST = socket.gethostname().split(".")[0]
EARTH = os.path.join(HOME, ".local/share/mono-earth/frames.json")
MAIN_OUTPUT = os.environ.get("MONO_MAIN_OUTPUT", "")
HYPR_SOCK = os.path.join(RUN, "hypr", os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", ""), ".socket.sock")
DAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]

# цифры часов: 5 строк блоками
DIGITS = {
    "0": ["█████", "█   █", "█   █", "█   █", "█████"],
    "1": ["  ██ ", " ███ ", "  ██ ", "  ██ ", "█████"],
    "2": ["█████", "    █", "█████", "█    ", "█████"],
    "3": ["█████", "    █", " ████", "    █", "█████"],
    "4": ["█   █", "█   █", "█████", "    █", "    █"],
    "5": ["█████", "█    ", "█████", "    █", "█████"],
    "6": ["█████", "█    ", "█████", "█   █", "█████"],
    "7": ["█████", "    █", "   █ ", "  █  ", "  █  "],
    "8": ["█████", "█   █", "█████", "█   █", "█████"],
    "9": ["█████", "█   █", "█████", "    █", "█████"],
    ":": ["   ", " █ ", "   ", " █ ", "   "],
}

CSS = b"""
window { background: #000000; }
* { font-family: "Hack Nerd Font Mono", monospace; color: #ffffff; text-shadow: none; box-shadow: none; }
.clock { font-size: 22px; line-height: 1; }
.date { font-size: 15px; margin-top: 14px; }
.earth { font-size: 10px; color: rgba(255,255,255,0.55); margin: 26px 0; }
.prompt { font-size: 15px; }
.pw {
  background: #000000; border: 1px solid #ffffff; border-radius: 999px;
  min-height: 46px; min-width: 340px; padding: 0 20px; font-size: 16px; caret-color: #ffffff;
}
.pw:focus-within { border-width: 2px; }
.pw text selection { background: #ffffff; color: #000000; }
.status { font-size: 13px; min-height: 20px; margin-top: 12px; }
.status.err { font-weight: bold; }
.hint { font-size: 12px; color: rgba(255,255,255,0.5); margin-top: 6px; }
"""


def hypr_json(what):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(HYPR_SOCK)
            s.sendall(f"j/{what}".encode())
            data = b""
            while True:
                c = s.recv(65536)
                if not c:
                    break
                data += c
        return json.loads(data)
    except (OSError, ValueError):
        return None


def hypr_cmd(cmd):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(HYPR_SOCK)
            s.sendall(cmd.encode())
            s.recv(4096)
    except OSError:
        pass


def layout_index():
    d = hypr_json("devices") or {}
    kb = next((k for k in d.get("keyboards", []) if k.get("main")), None)
    return kb.get("active_layout_index", 0) if kb else 0


def big_clock():
    rows = ["", "", "", "", ""]
    for ch in time.strftime("%H:%M"):
        for i in range(5):
            rows[i] += DIGITS[ch][i] + " "
    return "\n".join(r.rstrip() for r in rows)


def date_line():
    t = time.localtime()
    return f"{DAYS[t.tm_wday]}, {t.tm_mday} {MONTHS[t.tm_mon - 1]}"


def layout_name():
    d = hypr_json("devices") or {}
    kb = next((k for k in d.get("keyboards", []) if k.get("main")), None)
    return "RU" if kb and "Russian" in kb.get("active_keymap", "") else "EN"


class Screen(Gtk.Window):
    """один экран блокировки на монитор, на каждом своё поле пароля"""

    def __init__(self, app, lock, monitor, frames, main):
        super().__init__(application=app)
        self.app, self.frames, self.main = app, frames, main
        lock.assign_window_to_monitor(self, monitor)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.clock = Gtk.Label(label=big_clock(), justify=Gtk.Justification.CENTER)
        self.clock.add_css_class("clock")
        self.date = Gtk.Label(label=date_line())
        self.date.add_css_class("date")
        self.earth = Gtk.Label(justify=Gtk.Justification.LEFT, xalign=0)
        self.earth.add_css_class("earth")
        self.earth.set_halign(Gtk.Align.CENTER)
        col.append(self.clock)
        col.append(self.date)
        col.append(self.earth)

        if main:
            prompt = Gtk.Label(label=f"{USER}@{HOST} ~ $ unlock")
            prompt.add_css_class("prompt")
            prompt.set_margin_bottom(12)
            col.append(prompt)
            self.pw = Gtk.PasswordEntry()
            self.pw.add_css_class("pw")
            self.pw.set_halign(Gtk.Align.CENTER)
            self.pw.connect("activate", lambda *_: app.try_unlock(self))
            col.append(self.pw)
            self.status = Gtk.Label(label="")
            self.status.add_css_class("status")
            col.append(self.status)
            self.hint = Gtk.Label(label="")
            self.hint.add_css_class("hint")
            col.append(self.hint)
        self.set_child(col)

    def set_hint(self, layout):
        if self.main:
            self.hint.set_text(f"раскладка {layout} · enter")

    def tick_clock(self):
        self.clock.set_text(big_clock())
        self.date.set_text(date_line())

    def tick_earth(self, i):
        if self.frames:
            self.earth.set_text("\n".join(self.frames[i % len(self.frames)]))

    def say(self, text, err=False):
        self.status.set_text(text)
        (self.status.add_css_class if err else self.status.remove_css_class)("err")

    def shake(self):
        steps = [16, -14, 10, -8, 5, -3, 0]

        def step(k=[0]):
            if k[0] >= len(steps):
                self.pw.set_margin_start(0)
                self.pw.set_margin_end(0)
                return False
            d = steps[k[0]]
            self.pw.set_margin_start(max(0, d) * 2)
            self.pw.set_margin_end(max(0, -d) * 2)
            k[0] += 1
            return True
        GLib.timeout_add(35, step)


class LockApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="dev.mono.lock", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.screens = []
        self.busy = False
        self.frame = 0
        self.prev_layout = 0
        try:
            self.frames = json.load(open(EARTH))["frames"]
        except (OSError, ValueError, KeyError):
            self.frames = []
        self.connect("activate", self.on_activate)

    def on_activate(self, _app):
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self.hold()
        self.lock = SL.Instance.new()
        self.lock.connect("monitor", self.on_monitor)
        self.lock.connect("locked", self.on_locked)
        self.lock.connect("failed", lambda *_: self.quit())
        self.lock.connect("unlocked", lambda *_: self.on_unlocked())
        if not self.lock.lock():
            self.quit()
            return
        GLib.timeout_add_seconds(1, self.tick_clock)
        GLib.timeout_add(100, self.tick_earth)
        test = os.environ.get("MONO_LOCK_TEST")
        if test:
            GLib.timeout_add_seconds(int(test), lambda: (self.lock.unlock(), False)[1])

    def on_monitor(self, _lock, monitor):
        # поле пароля на КАЖДОМ мониторе: Hyprland отдаёт клавиатуру экрану блокировки того
        # монитора, где фокус. Если поле только на одном, ввод может уйти на экран без поля
        # (например, на спящий второй монитор) и разблокироваться будет нечем.
        s = Screen(self, self.lock, monitor, self.frames, True)
        self.screens.append(s)
        s.present()
        s.pw.grab_focus()

    def on_locked(self, _lock):
        # экран уже под замком: обёртка mono-lock отпускает swayidle, и только тогда идёт сон
        open(READY, "w").close()
        # пароль латиницей: включаем первую раскладку (us), после разблокировки вернём прежнюю
        self.prev_layout = layout_index()
        hypr_cmd("switchxkblayout all 0")
        self.tick_layout()

    def tick_clock(self):
        for s in self.screens:
            s.tick_clock()
        self.tick_layout()
        return True

    def tick_layout(self):
        lay = layout_name()
        for s in self.screens:
            s.set_hint(lay)

    def on_unlocked(self):
        if self.prev_layout:
            hypr_cmd(f"switchxkblayout all {self.prev_layout}")
        self.quit()

    def tick_earth(self):
        self.frame += 1
        for s in self.screens:
            s.tick_earth(self.frame)
        return True

    def try_unlock(self, screen):
        if self.busy:
            return
        password = screen.pw.get_text()
        if not password:
            return
        self.busy = True
        screen.pw.set_sensitive(False)
        screen.say("проверка...")

        def work():
            ok = False
            try:
                ok = pam.pam().authenticate(USER, password, service="swaylock")
            except Exception:
                ok = False
            GLib.idle_add(done, ok)

        def done(ok):
            self.busy = False
            if ok:
                screen.say("доступ разрешён")
                self.lock.unlock()
            else:
                screen.pw.set_sensitive(True)
                screen.pw.set_text("")
                screen.pw.grab_focus()
                screen.say("доступ запрещён", err=True)
                screen.shake()
            return False
        threading.Thread(target=work, daemon=True).start()


def main():
    try:
        pid = int(open(PID).read())
        os.kill(pid, 0)
        return  # уже заблокировано
    except (FileNotFoundError, ValueError, ProcessLookupError):
        pass

    open(PID, "w").write(str(os.getpid()))
    try:
        LockApp().run([])
    finally:
        for f in (READY,):
            try:
                os.remove(f)
            except FileNotFoundError:
                pass
        try:
            if open(PID).read().strip() == str(os.getpid()):
                os.remove(PID)
        except (FileNotFoundError, ValueError):
            pass


if __name__ == "__main__":
    main()
