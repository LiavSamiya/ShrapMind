#!/usr/bin/env bash
# Bring up Postgres + the backend, then seed only if the knowledge base is empty.
set -euo pipefail
cd "$(dirname "$0")/../.."

c_blue=$'\033[34m'; c_green=$'\033[32m'; c_off=$'\033[0m'
log() { printf '%s==>%s %s\n' "$c_blue" "$c_off" "$*"; }
ok()  { printf '%s  ok%s %s\n' "$c_green" "$c_off" "$*"; }

if [[ ! -f .env ]]; then
  echo "No .env found. Copy .env.example to .env and fill it in:" >&2
  echo "  cp .env.example .env" >&2
  exit 1
fi

# Load .env line by line WITHOUT eval, so a value containing shell
# metacharacters cannot execute anything.
log "loading .env"
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" == \#* || "$line" != *=* ]] && continue
  key="${line%%=*}"; val="${line#*=}"
  key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
  val="${val#"${val%%[![:space:]]*}"}"; val="${val%"${val##*[![:space:]]}"}"
  val="${val%\"}"; val="${val#\"}"; val="${val%\'}"; val="${val#\'}"
  export "$key=$val"
done < .env

: "${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}"
: "${WORKER_TOKEN:?set WORKER_TOKEN in .env}"

PORT="${APP_PORT:-7860}"

log "starting the stack"
docker compose up -d

log "waiting for /health"
for i in $(seq 1 60); do
  if curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
    ok "backend is up"
    break
  fi
  [[ $i -eq 60 ]] && { echo "backend did not come up; docker compose logs backend" >&2; exit 1; }
  sleep 5
done

log "checking the knowledge base"
count="$(docker compose exec -T postgres psql -tA \
  -U "${POSTGRES_USER:-shrapmind}" -d "${POSTGRES_DB:-shrapmind}" \
  -c 'select count(*) from enzyme_families' 2>/dev/null | tr -d '[:space:]' || echo 0)"
if [[ "${count:-0}" == "0" ]]; then
  log "empty - seeding"
  docker compose exec -T backend python -m server.db.seed
  ok "seeded"
else
  ok "already has ${count} enzyme families - not reseeding"
fi

docker compose ps
cat <<EOF

  console   http://localhost:${PORT}/
  reviewer  http://localhost:${PORT}/review
  health    http://localhost:${PORT}/health

  Start the simulation worker (it dials out to the backend):

    pip install -r client/worker/requirements.txt
    python -m client.worker.main --backend ws://localhost:${PORT} --token "\$WORKER_TOKEN"

  Follow logs:  docker compose logs -f backend
  Stop:         ./server/scripts/stop_all.sh
EOF
