"""FastAPI backend for the biologists' review queue.

Same role as voodo's server/app/main.py: serve a dashboard, expose the DB
layer over HTTP, gate the writes behind a password.

The one endpoint that matters is POST /api/changes/{id}/review. Everything
the engine wants to assert about biology waits there until a person answers,
and approving is the only path by which anything reaches `proposals`. The
engine cannot write to the answer set on its own — not as a policy the code
asks nicely about, but because no other function inserts into that table.
"""
from __future__ import annotations

import logging
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles

from server.db import client
from shared.config import settings
from shared.protocol import ProposalRecord, ReviewDecision

log = logging.getLogger("shrapmind.app")
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="ShrapMind — review queue", version="0.1")
security = HTTPBasic(auto_error=False)


def reviewer(creds: HTTPBasicCredentials | None = Depends(security)) -> str:
    """Gate the write endpoints.

    Fails closed: with no REVIEWER_PASSWORD set, nobody can review. An open
    approval endpoint would let anyone promote a claim about an enzyme into
    the answer set, which is worse than a dashboard that refuses to work.
    """
    if not settings.reviewer_password:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "REVIEWER_PASSWORD is not set; review is disabled.",
        )
    ok = (
        creds is not None
        and secrets.compare_digest(creds.username, settings.reviewer_username)
        and secrets.compare_digest(creds.password, settings.reviewer_password)
    )
    if not ok:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds.username


# ── Read ─────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict:
    """Also reports which embedder is live, because a reviewer reading
    'similar cases' needs to know what kind of similar they are seeing."""
    try:
        pending = len(client.get_pending_changes(status="pending"))
        db_ok = True
    except Exception as err:  # noqa: BLE001
        log.warning("health: db unreachable (%s)", err)
        pending, db_ok = 0, False
    return {
        "ok": db_ok,
        "pending": pending,
        "embedding": client.embedding_kind(),
        "similarity_threshold": settings.similarity_threshold,
        "review_enabled": bool(settings.reviewer_password),
    }


@app.get("/api/changes")
def changes(status_filter: str | None = Query(default=None, alias="status")) -> list[dict]:
    return client.get_pending_changes(status=status_filter)


@app.get("/api/proposals")
def proposals(limit: int = Query(default=100, ge=1, le=500)) -> list[ProposalRecord]:
    """What biologists have approved. Empty until someone does."""
    return client.get_all_proposals(limit=limit)


@app.get("/api/search")
def search(q: str = Query(min_length=2), top_k: int = Query(default=3, ge=1, le=20)) -> dict:
    """Nearest approved cases, with the threshold applied rather than hidden.

    `above_threshold` is what the engine would treat as "already answered".
    Returning the raw neighbours too lets a reviewer see a near-miss and
    judge it, instead of the system silently deciding it was close enough.
    """
    matches = client.search_similar(q, top_k=top_k)
    return {
        "embedding": client.embedding_kind(),
        "threshold": settings.similarity_threshold,
        "above_threshold": [
            m.model_dump() for m in matches
            if m.score >= settings.similarity_threshold
        ],
        "matches": [m.model_dump() for m in matches],
    }


@app.get("/api/notes/similar")
def similar_notes(q: str = Query(min_length=2), top_k: int = Query(default=5, ge=1, le=20)) -> list[dict]:
    """Objections already raised, so the same hour is not spent twice."""
    return client.search_review_notes(q, top_k=top_k)


@app.get("/api/experiments")
def experiments() -> list[dict]:
    """The bench queue: what reviewers independently said needs measuring."""
    return client.open_experiments()


# ── Write ────────────────────────────────────────────────────────────────────

@app.post("/api/changes/{change_id}/review")
def review(change_id: str, decision: ReviewDecision, who: str = Depends(reviewer)) -> dict:
    """Answer a queued item.

    'agree' writes the claim into `proposals` at `expert_review`. Every other
    verdict closes the item without writing anything — including
    'needs_experiment', which is not a softer rejection but the most useful
    answer available: it names a measurement that does not exist yet, and it
    is the one that reaches the `open_experiments` view.
    """
    # The dashboard's identity, not the client's claim about it.
    decision = decision.model_copy(update={"reviewer": who})
    try:
        if decision.verdict == "agree":
            ok = client.approve_pending_change(change_id, decision)
        else:
            ok = client.reject_pending_change(change_id, decision)
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    if not ok:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No pending change with that id (already reviewed, or unknown).",
        )
    return {"ok": True, "change_id": change_id, "verdict": decision.verdict}


@app.post("/api/feedback")
def feedback(rating: str, proposal_id: str | None = None, summary: str | None = None) -> dict:
    if not client.save_feedback(rating, proposal_id=proposal_id, summary=summary):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "rating must be like or dislike")
    return {"ok": True}


# ── Static ───────────────────────────────────────────────────────────────────

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
