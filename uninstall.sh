#!/usr/bin/env bash
# blackrise: откат. Возвращает конфиги из последнего бэкапа install.sh и отключает райс в hyprland.conf.
# Пакеты не удаляет. Тему загрузки вернуть: sudo plymouth-set-default-theme -R bgrt
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
last="$HOME/.local/share/blackrise-backup/last"
[ -f "$last" ] || { echo "бэкап не найден: install.sh не запускался"; exit 1; }
backup="$(cat "$last")"

for f in "$here"/bin/*; do rm -f "$HOME/.local/bin/$(basename "$f")"; done
rm -rf "$HOME/.local/lib/mono" "$HOME/.config/hypr/mono"
[ -d "$backup/bin" ] && cp -a "$backup"/bin/. "$HOME/.local/bin/"
[ -d "$backup/config" ] && cp -a "$backup"/config/. "$HOME/.config/"
if [ -f "$backup/hyprland.conf" ]; then
  cp -a "$backup/hyprland.conf" "$HOME/.config/hypr/hyprland.conf"
else
  sed -i '\#source = ~/.config/hypr/mono/#d' "$HOME/.config/hypr/hyprland.conf"
fi
echo "откат готов: конфиги из $backup"
