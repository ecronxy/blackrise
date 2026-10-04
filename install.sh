#!/usr/bin/env bash
# blackrise: установка чёрно-белого райса Hyprland на Fedora.
#   ./install.sh            поставить пакеты, шрифт, курсор и конфиги (старые сохраняются в бэкап)
#   ./install.sh --no-deps  только конфиги и скрипты, без dnf
#   ./install.sh --boot     ещё и тема загрузки (Plymouth, пересоберёт initramfs)
# Откат: ./uninstall.sh
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
backup="$HOME/.local/share/blackrise-backup/$(date +%Y%m%d-%H%M%S)"
deps=1 boot=0
for a in "$@"; do
  case "$a" in
    --no-deps) deps=0 ;;
    --boot) boot=1 ;;
    *) echo "неизвестный ключ: $a"; exit 1 ;;
  esac
done

say() { printf '\n\033[1m> %s\033[0m\n' "$*"; }

if [ "$deps" = 1 ]; then
  say "пакеты (нужен sudo)"
  sudo dnf -y copr enable solopasha/hyprland
  sudo dnf -y copr enable scottames/ghostty
  sudo dnf -y install hyprland hyprpaper hyprpicker xdg-desktop-portal-hyprland xdg-desktop-portal-gnome \
    ghostty fastfetch nautilus gnome-control-center \
    gtk4-layer-shell python3-gobject python3-pam python3-pillow \
    swaync wlogout wofi swayidle swaylock grim slurp wf-recorder wl-clipboard \
    playerctl brightnessctl wireplumber libnotify network-manager-applet mate-polkit power-profiles-daemon \
    curl unzip
fi

say "шрифт Hack Nerd Font и курсор Bibata"
mkdir -p "$HOME/.local/share/fonts" "$HOME/.local/share/icons"
if ! fc-list | grep -q "Hack Nerd Font Mono"; then
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/Hack.zip" https://github.com/ryanoasis/nerd-fonts/releases/latest/download/Hack.zip
  unzip -oq "$tmp/Hack.zip" 'HackNerdFontMono-*.ttf' -d "$HOME/.local/share/fonts"
  fc-cache -f >/dev/null
  rm -rf "$tmp"
fi
if [ ! -d "$HOME/.local/share/icons/Bibata-Modern-Classic" ]; then
  curl -fsSL https://github.com/ful1e5/Bibata_Cursor/releases/latest/download/Bibata-Modern-Classic.tar.xz \
    | tar -xJ -C "$HOME/.local/share/icons"
fi

say "бэкап текущих конфигов: $backup"
mkdir -p "$backup"
for d in hypr/mono ghostty fastfetch swaync wlogout wofi/mono gtk-4.0/gtk.css swaylock/mono; do
  [ -e "$HOME/.config/$d" ] && { mkdir -p "$backup/config/$(dirname "$d")"; cp -a "$HOME/.config/$d" "$backup/config/$d"; }
done
[ -f "$HOME/.config/hypr/hyprland.conf" ] && cp -a "$HOME/.config/hypr/hyprland.conf" "$backup/hyprland.conf"
mkdir -p "$backup/bin"
for f in "$here"/bin/*; do
  [ -e "$HOME/.local/bin/$(basename "$f")" ] && cp -a "$HOME/.local/bin/$(basename "$f")" "$backup/bin/"
done
echo "$backup" > "$HOME/.local/share/blackrise-backup/last"

say "конфиги и скрипты"
mkdir -p "$HOME/.config" "$HOME/.local/bin" "$HOME/.local/lib/mono" "$HOME/.local/share"
cp -a "$here"/config/. "$HOME/.config/"
sed -i "s#@HOME@#$HOME#g" "$HOME/.config/wlogout/style.css"
install -m755 "$here"/bin/* "$HOME/.local/bin/"
cp -a "$here"/lib/mono/. "$HOME/.local/lib/mono/"
for d in mono-icons mono-earth; do
  rm -rf "$HOME/.local/share/$d"
  cp -a "$here/share/$d" "$HOME/.local/share/$d"
done
mkdir -p "$HOME/.local/share/mono-themes" "$HOME/.local/share/vscode-mono"
cp -a "$here"/share/themes/. "$HOME/.local/share/mono-themes/"
cp -a "$here"/share/vscode-mono/. "$HOME/.local/share/vscode-mono/"

# hyprland.conf подключает райс одной строкой; свой конфиг остаётся ниже и может что-то переопределить
conf="$HOME/.config/hypr/hyprland.conf"
touch "$conf"
grep -q 'source = ~/.config/hypr/mono/main.conf' "$conf" || {
  printf '%s\n%s\n\n' 'source = ~/.config/hypr/mono/main.conf' 'source = ~/.config/hypr/mono/autostart.conf' \
    | cat - "$conf" > "$conf.new" && mv "$conf.new" "$conf"
}

gsettings set org.gnome.desktop.interface color-scheme prefer-dark 2>/dev/null || true
gsettings set org.gnome.desktop.interface cursor-theme Bibata-Modern-Classic 2>/dev/null || true

if [ "$boot" = 1 ]; then
  say "тема загрузки (Plymouth)"
  sudo rm -rf /usr/share/plymouth/themes/blackrise
  sudo cp -r "$here/share/plymouth-blackrise" /usr/share/plymouth/themes/blackrise
  sudo plymouth-set-default-theme -R blackrise
fi

say "готово"
cat <<'EOF'
Выйди из сессии и выбери Hyprland на экране входа.
Основной монитор (док, центр управления, блокировка): в ~/.config/hypr/mono/main.conf
раскомментируй строку env = MONO_MAIN_OUTPUT,<имя из hyprctl monitors>.
Откат: ./uninstall.sh
EOF
