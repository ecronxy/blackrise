#!/bin/sh
# Вставить скругления в VS Code. Запуск: sudo ~/.local/share/vscode-mono/apply.sh
# После обновления VS Code запустить снова. Откат: sudo ~/.local/share/vscode-mono/rollback.sh
set -eu
[ "$(id -u)" -eq 0 ] || { echo "запусти через sudo"; exit 1; }
H=$(getent passwd "${SUDO_USER:?}" | cut -d: -f6)
F=/usr/share/code/resources/app/out/vs/code/electron-browser/workbench/workbench.html
B="$H/.local/share/vscode-mono/workbench.html.orig"
[ -f "$F" ] || { echo "не нашёл $F"; exit 1; }
# копия оригинала: только если в файле ещё нет наших стилей
grep -q 'id="mono-css"' "$F" || cp "$F" "$B"
python3 - "$F" "$H/.local/share/vscode-mono/mono.css" <<'PY'
import re, sys
f, css = sys.argv[1], open(sys.argv[2]).read()
s = open(f).read()
s = re.sub(r'\n?<style id="mono-css">.*?</style>', '', s, flags=re.S)
s = s.replace("</head>", '<style id="mono-css">\n' + css + '</style>\n</head>', 1)
open(f, "w").write(s)
PY
chown "$SUDO_USER" "$B" 2>/dev/null || true
echo "Готово. Перезапусти VS Code. Плашку «установка повреждена» можно закрыть (Не показывать снова)."
