#!/usr/bin/env bash
# One virtualenv per component that reaches outside the process.
#
# Mirrors voodo's per-component requirements.txt split, with venvs so the
# components cannot quietly share a dependency they never declared.
#
# The boundaries, and why each one is where it is:
#
#   .venv-db     server/db      -> PostgreSQL, and HuggingFace on first model
#                                  download. Heavy and optional: installing
#                                  sentence-transformers pulls torch, which
#                                  nothing else should have to carry.
#   .venv-app    server/app     -> browsers. Web framework only; it reaches
#                                  the database through server.db, never with
#                                  its own driver.
#   .venv-tools  tools/         -> UniProt, NCBI, Crossref, RCSB, EBI. Today
#                                  it needs nothing beyond the standard
#                                  library; the venv exists so the day a
#                                  fetcher wants a dependency, it lands here
#                                  and not in the engine.
#
#   f2c/         no venv, by design. It is pure standard library and talks to
#                nothing. That is what makes `python -m pytest tests/` run on
#                a bare checkout with no install step, and it is worth
#                protecting: the moment the engine needs a wheel, the project
#                stops being auditable by someone who just cloned it.
#
# Usage:  bash server/scripts/setup_envs.sh [--with-embeddings]
set -euo pipefail

cd "$(dirname "$0")/../.."
ROOT="$PWD"
WITH_EMBEDDINGS="${1:-}"

make_env () {
    local name="$1" reqs="$2"
    echo "── $name  ($reqs)"
    if [ ! -d "$ROOT/$name" ]; then
        python3 -m venv "$ROOT/$name"
    fi
    "$ROOT/$name/bin/pip" install --quiet --upgrade pip
    if [ -s "$ROOT/$reqs" ] && grep -qvE '^\s*(#|$)' "$ROOT/$reqs"; then
        "$ROOT/$name/bin/pip" install --quiet -r "$ROOT/$reqs"
    else
        echo "   (no pinned dependencies yet — standard library only)"
    fi
}

make_env .venv-db    server/db/requirements.txt
make_env .venv-app   server/app/requirements.txt
make_env .venv-tools tools/requirements.txt

if [ "$WITH_EMBEDDINGS" = "--with-embeddings" ]; then
    echo "── adding sentence-transformers to .venv-db (large: pulls torch)"
    "$ROOT/.venv-db/bin/pip" install --quiet "sentence-transformers>=2.2"
fi

cat <<'DONE'

Environments ready.

  .venv-db/bin/python -m server.db.seed
  .venv-app/bin/uvicorn server.app.main:app --port 7870
  .venv-tools/bin/python tools/verify_sources.py --sample 40

The engine itself needs none of them:

  python -m pytest tests/ -q
  python -m f2c.cli select --material PET --mass-mg 50

Without --with-embeddings the database layer uses the built-in lexical
embedder. It matches wording rather than meaning, the dashboard says so, and
switching later means re-seeding (`python -m server.db.seed --reset`) because
vectors from the two embedders are not comparable.
DONE
