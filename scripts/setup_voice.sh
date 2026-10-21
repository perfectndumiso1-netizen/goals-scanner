#!/usr/bin/env bash
# Prepare the natural narration voice used by the PlayReport videos — locally or on a CI runner.
#
# It installs edge-tts (the same neural voice the workflow uses) into a private venv and downloads a
# Piper voice as an offline backup. Nothing here is committed: the models live in $VOICE_DIR.
#
#   bash scripts/setup_voice.sh                 # ~/.cache/playreport-voice
#   VOICE_DIR=/tmp/voice bash scripts/setup_voice.sh
#   eval "$(bash scripts/setup_voice.sh --export)"   # print the env vars to export instead
#
# After it runs, `python -m scanner` (or the breakdown/shortlist builders) speaks with the neural voice.
# Without it the builders refuse to publish a robot voice: see PLAYREPORT_ALLOW_ESPEAK in README.
set -euo pipefail

VOICE_DIR="${VOICE_DIR:-$HOME/.cache/playreport-voice}"
MODEL="$VOICE_DIR/en_GB-alan-medium.onnx"
CONFIG="$MODEL.json"
MODEL_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/alan/medium/en_GB-alan-medium.onnx"
CONFIG_URL="$MODEL_URL.json"
PY="$VOICE_DIR/venv/bin/python"

mkdir -p "$VOICE_DIR"

if [ ! -x "$PY" ]; then
  python3 -m venv "$VOICE_DIR/venv"
fi
"$VOICE_DIR/venv/bin/pip" install -q --upgrade pip
"$VOICE_DIR/venv/bin/pip" install -q --only-binary=:all: --retries 5 --timeout 60 edge-tts piper-tts==1.8.0

if [ ! -f "$MODEL" ] || [ ! -f "$CONFIG" ]; then
  curl -fsSL -o "$MODEL" "$MODEL_URL"
  curl -fsSL -o "$CONFIG" "$CONFIG_URL"
fi

# A one-line smoke test: does the neural voice actually answer from this machine?
if ! "$PY" -m edge_tts --voice "${EDGE_TTS_VOICE:-en-GB-RyanNeural}" --text "Voice check." \
      --write-media "$VOICE_DIR/check.mp3" >/dev/null 2>&1; then
  echo "warning: edge-tts could not reach the speech service from here; videos will use the Piper voice" >&2
fi
rm -f "$VOICE_DIR/check.mp3"

cat <<EOF
export EDGE_TTS_PYTHON="$PY"
export EDGE_TTS_VOICE="\${EDGE_TTS_VOICE:-en-GB-RyanNeural}"
export PIPER_PYTHON="$PY"
export PIPER_MODEL_PATH="$MODEL"
export PIPER_CONFIG_PATH="$CONFIG"
EOF

if [ "${1:-}" = "--export" ]; then
  exit 0
fi
echo
echo "Voice ready. Export the lines above (or 'eval \"\$(bash scripts/setup_voice.sh --export)\"') before building a video."
