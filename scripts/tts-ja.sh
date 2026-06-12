#!/usr/bin/env bash
set -euo pipefail

VOICE_DEFAULT="ja-JP-NanamiNeural"
EDGE_TTS_VENV="${EDGE_TTS_VENV:-${HOME}/.venvs/edge-tts}"
EDGE_TTS_BIN="${EDGE_TTS_BIN:-${EDGE_TTS_VENV}/bin/edge-tts}"
OUT_DIR_DEFAULT="${TTS_OUT_DIR:-${HOME}/tts-output}"

usage() {
  cat <<'EOF'
Usage:
  tts-ja.sh "日本語テキスト"
  tts-ja.sh -f input.txt
  tts-ja.sh -o output.mp3 "日本語テキスト"
  tts-ja.sh -v ja-JP-KeitaNeural "日本語テキスト"

Options:
  -f FILE   Read text from file
  -o FILE   Output mp3 path
  -v VOICE  Edge TTS voice (default: ja-JP-NanamiNeural)
  -h        Show help
EOF
}

if [[ ! -x "$EDGE_TTS_BIN" ]]; then
  echo "edge-tts not found: $EDGE_TTS_BIN" >&2
  echo "Install it first (see install.sh) or set EDGE_TTS_VENV / EDGE_TTS_BIN" >&2
  exit 1
fi

voice="$VOICE_DEFAULT"
out=""
text_file=""
text=""

while getopts ":f:o:v:h" opt; do
  case "$opt" in
    f) text_file="$OPTARG" ;;
    o) out="$OPTARG" ;;
    v) voice="$OPTARG" ;;
    h)
      usage
      exit 0
      ;;
    :)
      echo "Option -$OPTARG requires an argument" >&2
      usage >&2
      exit 1
      ;;
    \?)
      echo "Unknown option: -$OPTARG" >&2
      usage >&2
      exit 1
      ;;
  esac
done
shift $((OPTIND - 1))

if [[ -n "$text_file" ]]; then
  if [[ ! -f "$text_file" ]]; then
    echo "Text file not found: $text_file" >&2
    exit 1
  fi
  text="$(cat "$text_file")"
elif [[ $# -gt 0 ]]; then
  text="$*"
else
  echo "No text provided" >&2
  usage >&2
  exit 1
fi

if [[ -z "${text//[[:space:]]/}" ]]; then
  echo "Text is empty" >&2
  exit 1
fi

mkdir -p "$OUT_DIR_DEFAULT"

if [[ -z "$out" ]]; then
  ts="$(date +%Y%m%d-%H%M%S)"
  out="$OUT_DIR_DEFAULT/tts-ja-$ts.mp3"
fi

mkdir -p "$(dirname "$out")"

"$EDGE_TTS_BIN" \
  --voice "$voice" \
  --text "$text" \
  --write-media "$out"

echo "$out"
