#!/usr/bin/env bash
set -euo pipefail
FRAMEWORK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$FRAMEWORK_ROOT"
source "$FRAMEWORK_ROOT/scripts/launcher-common.sh"
launcher_options "$@"
command -v docker >/dev/null 2>&1 || { echo "Install Docker Desktop or Docker Engine to use this launcher." >&2; exit 1; }
docker info --format '{{.ServerVersion}}' >/dev/null 2>&1 || { echo "Start Docker Desktop or the Docker daemon, then try again." >&2; exit 1; }
launcher_directories
IMAGE="${GPTAPPS_DOCKER_IMAGE:-gpt-generated-app:local}"
CONTAINER="${GPTAPPS_CONTAINER_NAME:-gpt-generated-app-$PORT}"
if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "Container $CONTAINER already exists. Stop it first or set GPTAPPS_CONTAINER_NAME to another name." >&2
  exit 1
fi
docker build --tag "$IMAGE" "$FRAMEWORK_ROOT"
CONFIGURED_MODEL=""
if [[ -z "${OPENAI_MODEL:-}" ]]; then
  CONFIGURED_MODEL="$(docker run --rm --user "$(id -u):$(id -g)" \
    --volume "$FRAMEWORK_ROOT/app.json:/config/app.json:ro" "$IMAGE" \
    python -c 'from gptapps.spec import load; print(load("/config/app.json")["runtime"].get("model") or "")')"
fi
launcher_credentials "$CONFIGURED_MODEL"
docker run --detach --rm --init --name "$CONTAINER" \
  --user "$(id -u):$(id -g)" --publish "127.0.0.1:$PORT:$PORT" \
  --env OPENAI_API_KEY --env OPENAI_MODEL \
  --env "GPTAPPS_PORT=$PORT" \
  --volume "$FRAMEWORK_ROOT/app.json:/config/app.json:ro" --volume "$DATA_DIR:/data" \
  "$IMAGE" >/dev/null
LOG_PID=""
cleanup() {
  trap - EXIT INT TERM
  if [[ -n "$LOG_PID" ]]; then kill "$LOG_PID" 2>/dev/null || true; fi
  docker stop --time 5 "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
READY=0
for ((attempt=0; attempt<60; attempt++)); do
  HEALTH="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER" 2>/dev/null || true)"
  if [[ "$HEALTH" == healthy ]]; then READY=1; break; fi
  if [[ -z "$HEALTH" || "$HEALTH" == unhealthy || "$HEALTH" == exited ]]; then break; fi
  sleep 1
done
if [[ "$READY" != 1 ]]; then
  docker logs "$CONTAINER" >&2 || true
  echo "The container did not become ready. Check the error above and whether port $PORT is available." >&2
  exit 1
fi
echo "Application ready: $URL — press Ctrl+C to stop the container."
launcher_browser
docker logs --follow "$CONTAINER" &
LOG_PID=$!
wait "$LOG_PID"
