#!/usr/bin/env bash
#
# Bootstrap the daily-japanese-anki skill on a fresh machine.
#
#   - creates a Python venv (default: ~/.venvs/edge-tts)
#   - installs requirements.txt into it
#   - checks that Anki + AnkiConnect are reachable on port 8765
#
# Override the venv location with EDGE_TTS_VENV=/path ./install.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EDGE_TTS_VENV="${EDGE_TTS_VENV:-${HOME}/.venvs/edge-tts}"
PYTHON="${PYTHON:-python3}"
ANKI_URL="${ANKI_URL:-http://localhost:8765}"

echo "==> Skill dir : $SCRIPT_DIR"
echo "==> venv      : $EDGE_TTS_VENV"

# 1. venv + deps -------------------------------------------------------------
if [[ ! -x "${EDGE_TTS_VENV}/bin/python" ]]; then
  echo "==> Creating venv"
  "$PYTHON" -m venv "$EDGE_TTS_VENV"
fi
echo "==> Installing Python dependencies"
"${EDGE_TTS_VENV}/bin/pip" install --quiet --upgrade pip
"${EDGE_TTS_VENV}/bin/pip" install --quiet -r "${SCRIPT_DIR}/requirements.txt"

# 2. make scripts executable -------------------------------------------------
chmod +x "${SCRIPT_DIR}/scripts/"*.sh 2>/dev/null || true

# 3. AnkiConnect reachability check -----------------------------------------
echo "==> Checking AnkiConnect at ${ANKI_URL}"
if curl -s --fail --max-time 3 "$ANKI_URL" \
     -d '{"action":"version","version":6}' >/dev/null 2>&1; then
  echo "    OK — AnkiConnect is responding."
else
  cat <<EOF
    WARNING — could not reach AnkiConnect at ${ANKI_URL}.
    Make sure Anki is running and the AnkiConnect add-on is installed:
      Anki -> Tools -> Add-ons -> Get Add-ons -> code 2055492159
    (This is only needed at run time, not for install.)
EOF
fi

cat <<EOF

==> Done.

To use the skill, add cards with:
  ${EDGE_TTS_VENV}/bin/python ${SCRIPT_DIR}/scripts/daily_japanese_add.py --help

If you put the venv somewhere non-default, export EDGE_TTS_VENV so the
shell helpers can find it:
  export EDGE_TTS_VENV="$EDGE_TTS_VENV"
EOF
