#!/bin/sh
set -eu
if [ "$#" -gt 0 ]; then exec "$@"; fi
exec python -m gptapps serve --apps /config/app.json --data /data \
  --host 0.0.0.0 --port "${GPTAPPS_PORT:-8765}"
