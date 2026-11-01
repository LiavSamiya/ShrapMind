#!/usr/bin/env bash
# Stop the stack. The named volume survives, so the knowledge base persists.
set -euo pipefail
cd "$(dirname "$0")/../.."
docker compose down
echo "Stopped. The database volume (shrapmind-db-data) was kept."
echo "To wipe it too: docker compose down -v"
