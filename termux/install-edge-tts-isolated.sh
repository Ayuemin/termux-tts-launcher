#!/data/data/com.termux/files/usr/bin/bash
# Install a known-working Edge TTS version without changing global Termux pip packages.
set -euo pipefail

if [[ "${PREFIX:-}" != */com.termux/files/usr ]]; then
  echo 'Запусти установщик в обычном Termux (не Ubuntu/proot).' >&2
  exit 1
fi

VERSION=7.3.1
ROOT="$HOME/.local/share/termux-tts-launcher"
TARGET="$ROOT/edge-tts-$VERSION"
mkdir -p "$ROOT"

valid_install() {
  PYTHONPATH="$1" python - "$1" <<'PY'
import importlib.metadata
import pathlib
import sys
import edge_tts
base = pathlib.Path(sys.argv[1]).resolve()
module = pathlib.Path(edge_tts.__file__).resolve()
assert module.is_relative_to(base), "Another edge-tts package was imported"
assert importlib.metadata.version("edge-tts") == "7.3.1", "Wrong Edge TTS version"
PY
}

if [[ -d "$TARGET" ]] && valid_install "$TARGET" >/dev/null 2>&1; then
  echo 'Локальная edge-tts 7.3.1 уже установлена.'
  exit 0
fi

STAGING=$(mktemp -d "$ROOT/.install-edge-tts.XXXXXX")
trap 'rm -rf -- "$STAGING"' EXIT
python -m pip install --no-deps --disable-pip-version-check \
  --target "$STAGING" 'edge-tts==7.3.1'
if ! valid_install "$STAGING"; then
  echo 'Изолированная версия не прошла проверку, существующая установка не тронута.' >&2
  exit 1
fi
# This is an app-owned, version-specific directory, never a shared pip location.
if [[ -d "$TARGET" ]]; then
  mv "$TARGET" "$ROOT/.edge-tts-previous-$$"
  PREVIOUS="$ROOT/.edge-tts-previous-$$"
fi
mv "$STAGING" "$TARGET"
if [[ -n "${PREVIOUS:-}" && -d "$PREVIOUS" ]]; then rm -rf -- "$PREVIOUS"; fi
echo "Установлена локальная edge-tts $VERSION: $TARGET"
