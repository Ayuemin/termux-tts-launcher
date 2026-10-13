#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$PREFIX/bin/tts-launcher-play"
if [[ "${PREFIX:-}" != */com.termux/files/usr ]]; then
  echo 'Запустите установщик в Termux (не в Ubuntu/proot).'; exit 1
fi
if [[ ! -f "$HERE/tts-launcher-play" ]]; then
  echo 'Рядом со скриптом установки отсутствует tts-launcher-play.'; exit 1
fi
if ! command -v python >/dev/null || ! command -v termux-media-player >/dev/null; then
  echo 'Устанавливаю только Python и утилиты Termux:API...'
  pkg install -y python termux-api
fi
if ! command -v edge-tts >/dev/null; then
  echo 'Устанавливаю edge-tts (без браузера и FFmpeg)...'
  python -m pip install edge-tts
fi
# Prefer the repaired Edge TTS locally without upgrading anyone else's packages.
bash "$HERE/install-edge-tts-isolated.sh"
install -m 755 "$HERE/tts-launcher-play" "$TARGET"
echo "Готово: $TARGET"
echo 'Используется изолированная edge-tts 7.3.1; глобальные Python-пакеты не обновлены.'
echo 'Новая команда: tts-launcher-play. Команда tts не изменена.'
echo 'Для воспроизведения нужно приложение Termux:API из того же источника, что и Termux.'
echo 'Один раз задайте allow-external-apps=true в ~/.termux/termux.properties.'
