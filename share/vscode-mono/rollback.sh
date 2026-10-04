#!/bin/sh
# Вернуть оригинальный файл VS Code. Запуск: sudo ~/.local/share/vscode-mono/rollback.sh
set -eu
[ "$(id -u)" -eq 0 ] || { echo "запусти через sudo"; exit 1; }
H=$(getent passwd "${SUDO_USER:?}" | cut -d: -f6)
F=/usr/share/code/resources/app/out/vs/code/electron-browser/workbench/workbench.html
cp "$H/.local/share/vscode-mono/workbench.html.orig" "$F"
echo "Возвращено. Тема (цвета) в settings.json; старые настройки: ~/.config/Code/User/settings.json.pre-mono-20261003"
