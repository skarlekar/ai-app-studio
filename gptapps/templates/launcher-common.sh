#!/usr/bin/env bash
# Shared launcher helpers. Credentials are never written to disk.
launcher_options() {
  PORT="${GPTAPPS_PORT:-8765}"
  DATA_DIR="${GPTAPPS_DATA_DIR:-$FRAMEWORK_ROOT/.gptapps-data}"
  OPEN_BROWSER=1
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --port|--data)
        [[ $# -ge 2 && -n "$2" ]] || { echo "Missing value for $1" >&2; exit 1; }
        case "$1" in
          --port) PORT="$2" ;;
          --data) DATA_DIR="$2" ;;
        esac
        shift 2 ;;
      --no-browser) OPEN_BROWSER=0; shift ;;
      -h|--help)
        echo "Usage: $0 [--port PORT] [--data DIRECTORY] [--no-browser]"
        echo "Starts this standalone app at http://127.0.0.1:PORT. Press Ctrl+C to stop."
        exit 0 ;;
      *) echo "Unknown option: $1. Use --help." >&2; exit 1 ;;
    esac
  done
  case "$PORT" in ''|*[!0-9]*) echo "Port must be between 1 and 65535." >&2; exit 1 ;; esac
  [[ ${#PORT} -le 5 ]] && (( 10#$PORT >= 1 && 10#$PORT <= 65535 )) || {
    echo "Port must be between 1 and 65535." >&2; exit 1;
  }
  PORT=$((10#$PORT))
  URL="http://127.0.0.1:$PORT"
}
launcher_credentials() {
  if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    [[ -t 0 ]] || { echo "Set OPENAI_API_KEY in the server environment, then run this launcher again." >&2; exit 1; }
    read -r -s -p "OpenAI API key (hidden; used only for this run): " OPENAI_API_KEY
    echo
    [[ -n "$OPENAI_API_KEY" ]] || { echo "An API key is required for app conversations." >&2; exit 1; }
  fi
  if [[ -z "${OPENAI_MODEL:-}" && -z "${1:-}" ]]; then
    [[ -t 0 ]] || { echo "Set OPENAI_MODEL to an available API model, then run this launcher again." >&2; exit 1; }
    read -r -p "OpenAI model ID (supports the app’s selected tools): " OPENAI_MODEL
    [[ -n "$OPENAI_MODEL" ]] || { echo "A model ID is required." >&2; exit 1; }
  fi
  export OPENAI_API_KEY OPENAI_MODEL
}
launcher_directories() {
  mkdir -p "$DATA_DIR"
  DATA_DIR="$(cd "$DATA_DIR" && pwd)"
}
launcher_browser() {
  [[ "$OPEN_BROWSER" == 1 ]] || return 0
  case "$(uname -s)" in
    Darwin) open "$URL" || echo "Open $URL in your browser." ;;
    MINGW*|MSYS*|CYGWIN*) cmd.exe /c start "" "$URL" || echo "Open $URL in your browser." ;;
    *)
      if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$URL" >/dev/null 2>&1 || echo "Open $URL in your browser."
      else
        echo "Open $URL in your browser."
      fi ;;
  esac
}
