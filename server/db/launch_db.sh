#!/usr/bin/env bash
# Run just Postgres + pgvector in Docker, without the rest of the stack.
# Useful when running the backend natively.
set -euo pipefail
cd "$(dirname "$0")"

IMAGE="${IMAGE:-pgvector/pgvector:pg16}"
NAME="${NAME:-shrapmind-db}"
PORT="${POSTGRES_PORT:-5432}"
VOLUME="${VOLUME:-shrapmind-db-data}"
USER="${POSTGRES_USER:-shrapmind}"
PASS="${POSTGRES_PASSWORD:-shrapmind}"
DB="${POSTGRES_DB:-shrapmind}"

echo "==> removing any existing container named ${NAME}"
docker rm -f "${NAME}" >/dev/null 2>&1 || true

echo "==> starting ${IMAGE}"
docker run -d --name "${NAME}" \
  -e POSTGRES_USER="${USER}" \
  -e POSTGRES_PASSWORD="${PASS}" \
  -e POSTGRES_DB="${DB}" \
  -p "${PORT}:5432" \
  -v "${VOLUME}:/var/lib/postgresql/data" \
  "${IMAGE}" >/dev/null

echo "==> waiting for Postgres"
for i in $(seq 1 30); do
  if docker exec "${NAME}" pg_isready -U "${USER}" -d "${DB}" >/dev/null 2>&1; then
    break
  fi
  [[ $i -eq 30 ]] && { echo "Postgres did not become ready" >&2; exit 1; }
  sleep 1
done

echo "==> applying schema.sql (idempotent)"
docker exec -i "${NAME}" psql -U "${USER}" -d "${DB}" < schema.sql >/dev/null

echo
echo "Ready. Put this in your .env:"
echo "  DATABASE_URL=postgresql://${USER}:${PASS}@localhost:${PORT}/${DB}"
echo
echo "Then seed it:  python -m server.db.seed"
