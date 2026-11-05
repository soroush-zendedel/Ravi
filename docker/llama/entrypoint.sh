#!/bin/sh
set -eu

configured_model="${RAVI_LOCAL_GGUF:-}"
model_path=""

if [ -n "$configured_model" ]; then
  normalized_model="$(printf '%s' "$configured_model" | sed 's#\\#/#g')"
  model_name="${normalized_model##*/}"
  model_path="$(find /models -type f -name "$model_name" -print -quit)"
  if [ -z "$model_path" ]; then
    echo "Configured GGUF model '$configured_model' was not found under /models." >&2
    exit 78
  fi
else
  model_path="$(find /models -type f -iname '*.gguf' -print -quit)"
  if [ -z "$model_path" ]; then
    echo "No GGUF model is available under /models. Pull a local model before enabling the llama profile." >&2
    exit 78
  fi
fi

exec /app/llama-server \
  --model "$model_path" \
  --host 0.0.0.0 \
  --port 8080 \
  --ctx-size "${RAVI_CONTEXT:-8192}" \
  --threads "${RAVI_THREADS:-4}"
