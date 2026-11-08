#!/usr/bin/env bash
set -euo pipefail
FRAMEWORK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$FRAMEWORK_ROOT"
source "$FRAMEWORK_ROOT/scripts/launcher-common.sh"
launcher_options "$@"
PYTHON_BIN="${GPTAPPS_PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi
if [[ -z "$PYTHON_BIN" ]] || ! "$PYTHON_BIN" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
  echo "Python 3.11 or newer is required. Install it or use ./docker-start.sh." >&2
  exit 1
fi
"$PYTHON_BIN" - "$PORT" <<'PY'
import socket
import sys
try:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', int(sys.argv[1])))
except OSError:
    sys.exit('This port is unavailable. Stop the existing app or choose --port ANOTHER_PORT.')
PY
launcher_credentials
launcher_directories
"$PYTHON_BIN" -m gptapps serve --apps "$APPS_DIR" --data "$DATA_DIR" --port "$PORT" --builder &
SERVER_PID=$!
cleanup() {
  trap - EXIT INT TERM
  if kill -0 "$SERVER_PID" 2>/dev/null; then kill "$SERVER_PID" 2>/dev/null || true; fi
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$PYTHON_BIN" - "$URL" "$SERVER_PID" <<'PY'
import json
import os
import sys
import time
import urllib.error
import urllib.request
for _ in range(100):
    try:
        os.kill(int(sys.argv[2]), 0)
        with urllib.request.urlopen(sys.argv[1] + '/api/config', timeout=.5) as response:
            if json.load(response).get('builder_enabled'):
                break
    except (OSError, ValueError, urllib.error.URLError):
        pass
    time.sleep(.1)
else:
    sys.exit('The framework did not become ready. Check the server error above.')
PY
echo "Framework ready: $URL — press Ctrl+C to stop."
launcher_browser
wait "$SERVER_PID"
