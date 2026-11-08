#!/bin/sh
set -eu
if [ "$#" -gt 0 ]; then exec "$@"; fi
exec python -m gptapps serve --apps /data/apps --data /data/runtime \
  --host 0.0.0.0 --port "${GPTAPPS_PORT:-8765}" --builder
