#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${PREFIX:-}" != */com.termux/files/usr ]]; then
  echo 'Установщик требует обычный Termux, не Ubuntu/proot.'; exit 1
fi
if [[ ! -f "$HERE/tts-launcher-stream" ]]; then
  echo 'Отсутствует экспериментальный обработчик.'; exit 1
fi
if ! command -v python >/dev/null; then pkg install -y python; fi
if ! python -c 'import edge_tts' >/dev/null 2>&1; then
  python -m pip install edge-tts
fi
install -m 755 "$HERE/tts-launcher-stream" "$PREFIX/bin/tts-launcher-stream"
echo 'Установлен только экспериментальный обработчик tts-launcher-stream.'
echo 'Команды tts и tts-launcher-play НЕ изменены.'
