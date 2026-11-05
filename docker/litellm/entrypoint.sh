#!/bin/sh
set -eu

python_bin=""
for candidate in /app/.venv/bin/python /app/.venv/bin/python3 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 \
    && "$candidate" -c 'import litellm' >/dev/null 2>&1; then
    python_bin="$candidate"
    break
  fi
done

if [ -z "$python_bin" ]; then
  echo "Unable to locate the Python interpreter used by LiteLLM." >&2
  exit 78
fi

patch_target="$($python_bin -c 'import litellm; from pathlib import Path; print(Path(litellm.__file__).resolve().parent / "llms/cloudflare/chat/transformation.py")')"
if [ ! -f "$patch_target" ]; then
  echo "The installed LiteLLM image does not contain the Cloudflare transformation module: $patch_target" >&2
  exit 78
fi

cp /opt/ravi/transformation.py "$patch_target"
exec litellm "$@"
