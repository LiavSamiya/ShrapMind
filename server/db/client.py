"""Database access. Flat module of functions - no ORM, no class, no pool.

Every call opens its own short-lived connection. At this scale that is
simpler than a pool and removes a whole class of "stale connection after the
container restarted" bug. If throughput ever matters, this is the one file
that has to change.

Resilience, in order of how often it saves you:
  - self-healing tables: a query against a missing table creates it and
    retries, so a fresh database needs no migration step
  - in-memory fallbacks: material notes work with Postgres down
  - per-row defensiveness: one malformed row is skipped and logged, it does
    not 500 the whole dashboard
  - approval-gated writes: the hot path can only ever write to the pending
    queue, never to the validated library
"""
from __future__ import annotations

import functools
import json
import logging
from typing import Any

from shared.config import settings
from shared.protocol import (
    AssayResult,
    DesignRun,
    DesignStep,
    EnzymeCandidate,
    FamilyMatch,
    FragmentPassport,
    PrecedentMatch,
    ReactionSpec,
    RunMatch,
    ToolCall,
)
from shared.safety import sanitize_for_prompt

log = logging.getLogger("shrapmind.db")

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]

EMBED_DIM = 384
_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def _connect() -> Any:
    if psycopg is None:
        raise RuntimeError("psycopg not installed - pip install -r server/db/requirements.txt")
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL not set in .env")
    return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=5)


# ------------------------------------------------------------------ embeddings


@functools.lru_cache(maxsize=1)
def _embedder() -> Any:
    """Load the sentence-transformer once per process. Lazy, because it is a
    multi-hundred-megabyte import that the CLI and mock paths never need."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(_MODEL_NAME)


def embed(text: str) -> list[float]:
    vec = _embedder().encode(text or "", normalize_embeddings=True)
    return [float(x) for x in vec]


def _vec_literal(vec: list[float]) -> str:
    """pgvector's textual input form."""
    return "[" + ",".join(f"{float(x):.7g}" for x in vec) + "]"


# ------------------------------------------------------------------ retrieval


def search_enzyme_families(query: str, top_k: int = 5,
                           material: str | None = None) -> list[FamilyMatch]:
    """Semantic search over enzyme families, optionally filtered by material.

    The material filter matters: cosine similarity over a short reaction
    description will happily rank a cellulase near a PETase because both are
    hydrolases, and designing the wrong chemistry confidently is the failure
    mode worth engineering against.
    """
    q = _vec_literal(embed(query))
    k = max(1, min(int(top_k), 25))
    sql = """
        select name, ec_class, reaction_class, substrate_material, kinetics,
               conditions, maturity, source,
               1 - (embedding <=> %s::vector) as score
        from enzyme_families
        where embedding is not null
    """
    params: list[Any] = [q]
    if material:
        sql += " and substrate_material = %s"
        params.append(material)
    sql += " order by embedding <=> %s::vector limit %s"
    params += [q, k]
    out: list[FamilyMatch] = []
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            for row in cur.fetchall():
                try:
                    out.append(FamilyMatch(
                        name=row["name"], ec_class=row["ec_class"],
                        reaction_class=row["reaction_class"],
                        substrate_material=row["substrate_material"],
                        kinetics=row["kinetics"] or {},
                        conditions=row["conditions"] or {},
                        source=row["source"], score=float(row["score"] or 0.0)))
                except Exception as e:  # noqa: BLE001
                    log.warning("skipping malformed enzyme_families row: %s", e)
    except Exception as e:  # noqa: BLE001
        log.warning("enzyme family search unavailable: %s", e)
    return out


def search_precedents(query: str, top_k: int = 3) -> list[PrecedentMatch]:
    q = _vec_literal(embed(query))
    k = max(1, min(int(top_k), 25))
    out: list[PrecedentMatch] = []
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("""
                select title, claim, what_it_proves, what_it_does_not_prove, citation,
                       1 - (embedding <=> %s::vector) as score
                from precedents where embedding is not null
                order by embedding <=> %s::vector limit %s
            """, (q, q, k))
            for row in cur.fetchall():
                try:
                    out.append(PrecedentMatch(
                        title=row["title"], claim=row["claim"],
                        what_it_proves=row["what_it_proves"],
                        what_it_does_not_prove=row["what_it_does_not_prove"],
                        citation=row["citation"], score=float(row["score"] or 0.0)))
                except Exception as e:  # noqa: BLE001
                    log.warning("skipping malformed precedents row: %s", e)
    except Exception as e:  # noqa: BLE001
        log.warning("precedent search unavailable: %s", e)
    return out


def search_similar_runs(case_summary: str, top_k: int = 3) -> list[RunMatch]:
    """Find prior design runs for a similar case. Feeds the agent's
    [TRUSTED SYSTEM HINT] splice, so everything that comes back out of here
    goes through sanitize_for_prompt before it reaches the model."""
    q = _vec_literal(embed(case_summary))
    k = max(1, min(int(top_k), 25))
    out: list[RunMatch] = []
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("""
                select id, case_summary, passport, reaction_spec, steps,
                       chosen_candidate, assay, success,
                       1 - (embedding <=> %s::vector) as score
                from design_runs where embedding is not null
                order by embedding <=> %s::vector limit %s
            """, (q, q, k))
            for row in cur.fetchall():
                rec = _row_to_run(row)
                if rec is not None:
                    out.append(RunMatch(record=rec, score=float(row["score"] or 0.0)))
    except Exception as e:  # noqa: BLE001
        log.warning("run search unavailable: %s", e)
    return out


def _row_to_run(row: dict[str, Any]) -> DesignRun | None:
    """Rehydrate a design_runs row, skipping individual steps whose tool name
    no longer exists in the ToolName Literal rather than failing the row."""
    try:
        steps: list[DesignStep] = []
        for s in row.get("steps") or []:
            try:
                steps.append(DesignStep(action=ToolCall(**s["action"]), note=s.get("note")))
            except Exception:  # noqa: BLE001
                continue
        passport = None
        if row.get("passport"):
            try:
                passport = FragmentPassport(**row["passport"])
            except Exception:  # noqa: BLE001
                pass
        spec = None
        if row.get("reaction_spec"):
            try:
                spec = ReactionSpec(**row["reaction_spec"])
            except Exception:  # noqa: BLE001
                pass
        cand = None
        if row.get("chosen_candidate"):
            try:
                cand = EnzymeCandidate(**row["chosen_candidate"])
            except Exception:  # noqa: BLE001
                pass
        assay = None
        if row.get("assay"):
            try:
                assay = AssayResult(**row["assay"])
            except Exception:  # noqa: BLE001
                pass
        return DesignRun(
            id=str(row["id"]), case_summary=row["case_summary"], passport=passport,
            reaction_spec=spec, steps=steps, chosen_candidate=cand, assay=assay,
            success=bool(row.get("success")))
    except Exception as e:  # noqa: BLE001
        log.warning("skipping malformed design_runs row: %s", e)
        return None


# ------------------------------------------------------------------ writes


def record_design_run(run: DesignRun) -> DesignRun:
    """Persist a completed run. Safe to call on the hot path - design_runs is
    a log, not the library, so nothing here is treated as validated."""
    steps = [{"action": s.action.model_dump(), "note": s.note} for s in run.steps]
    vec = _vec_literal(embed(run.case_summary))
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""
            insert into design_runs
                (case_summary, passport, reaction_spec, steps, chosen_candidate,
                 assay, success, embedding)
            values (%s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s::vector)
            returning id
        """, (
            run.case_summary,
            json.dumps(run.passport.model_dump() if run.passport else {}),
            json.dumps(run.reaction_spec.model_dump() if run.reaction_spec else {}),
            json.dumps(steps),
            json.dumps(run.chosen_candidate.model_dump()) if run.chosen_candidate else None,
            json.dumps(run.assay.model_dump()) if run.assay else None,
            run.success, vec))
        new_id = str(cur.fetchone()["id"])
        conn.commit()
    return run.model_copy(update={"id": new_id})


_ALLOWED_CHANGE_TYPES = {"add", "delete"}


def submit_pending_candidate(
    change_type: str,
    candidate_name: str,
    summary: str,
    *,
    material_family: str = "",
    rationale: str = "",
    candidate: dict[str, Any] | None = None,
    assay: dict[str, Any] | None = None,
    gates: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
    library_id: str | None = None,
    submitted_by: str = "agent",
) -> dict[str, Any]:
    """Queue a candidate for human scientific review.

    THE write chokepoint. Both the agent and the reviewer dashboard come
    through here, which is why every free-text field is sanitized in this
    function rather than at the call sites - a sanitizer that each caller has
    to remember is a sanitizer that one caller will forget.

    A candidate whose gates did not pass can still be submitted, because a
    documented failure is a result worth keeping; `gates_passed` is recorded
    so the reviewer sees it immediately and `approve_pending_candidate`
    refuses to promote it.
    """
    ct = str(change_type).lower()
    if ct not in _ALLOWED_CHANGE_TYPES:
        raise ValueError(f"change type must be one of {sorted(_ALLOWED_CHANGE_TYPES)}")
    gates = gates or []
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""
            insert into pending_candidates
                (type, library_id, candidate_name, material_family, summary, rationale,
                 candidate, assay, gates, run_id, submitted_by)
            values (%s, %s::uuid, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::uuid, %s)
            returning id, created_at
        """, (
            ct, library_id,
            sanitize_for_prompt(candidate_name, 200),
            sanitize_for_prompt(material_family, 80),
            sanitize_for_prompt(summary, 1000),
            sanitize_for_prompt(rationale, 2000),
            json.dumps(candidate or {}), json.dumps(assay or {}), json.dumps(gates),
            run_id, sanitize_for_prompt(submitted_by, 80)))
        row = cur.fetchone()
        conn.commit()
    return {"id": str(row["id"]), "created_at": row["created_at"].isoformat(),
            "status": "pending"}


def get_pending_candidates(status: str | None = None) -> list[dict[str, Any]]:
    sql = """select id, type, candidate_name, material_family, summary, rationale,
                    candidate, assay, gates, run_id, submitted_by, status,
                    reviewer_note, created_at, reviewed_at
             from pending_candidates"""
    params: list[Any] = []
    if status:
        sql += " where status = %s"
        params.append(status)
    sql += " order by created_at desc limit 200"
    out: list[dict[str, Any]] = []
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        for row in cur.fetchall():
            gates = row["gates"] or []
            out.append({
                "id": str(row["id"]), "type": row["type"],
                "candidate_name": row["candidate_name"],
                "material_family": row["material_family"],
                "summary": row["summary"], "rationale": row["rationale"],
                "candidate": row["candidate"] or {}, "assay": row["assay"] or {},
                "gates": gates,
                "gates_passed": bool(gates) and all(g.get("passed") for g in gates),
                "run_id": str(row["run_id"]) if row["run_id"] else None,
                "submitted_by": row["submitted_by"], "status": row["status"],
                "reviewer_note": row["reviewer_note"],
                "created_at": row["created_at"].isoformat(),
                "reviewed_at": row["reviewed_at"].isoformat() if row["reviewed_at"] else None,
            })
    return out


def approve_pending_candidate(change_id: str, reviewer_note: str | None = None,
                              approved_by: str = "reviewer") -> dict[str, Any]:
    """Promote a pending candidate into the validated library, in one
    transaction, computing the embedding at approval time.

    REFUSES to promote a candidate whose safety gates did not pass. A
    reviewer can reject, and can leave a note, but there is no button that
    promotes a gate failure - that would make the gates advisory, and an
    advisory gate is not a gate.
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""
            select id, type, library_id, candidate_name, material_family, summary,
                   candidate, assay, gates, status
            from pending_candidates where id = %s::uuid for update
        """, (change_id,))
        row = cur.fetchone()
        if row is None:
            return {"ok": False, "error": "no such pending candidate"}
        if row["status"] != "pending":
            return {"ok": False, "error": f"already {row['status']}"}

        gates = row["gates"] or []
        if row["type"] == "add":
            if not gates or not all(g.get("passed") for g in gates):
                failed = [g.get("name") for g in gates if not g.get("passed")] or ["no gates run"]
                return {"ok": False, "error": "cannot promote a candidate that did not "
                        f"pass its safety gates (failed: {', '.join(map(str, failed))}). "
                        "Reject it, or re-run the design with the failure addressed."}
            cur.execute("""
                insert into validated_library
                    (candidate_name, material_family, summary, candidate, assay, gates,
                     approved_by, reviewer_note, embedding)
                values (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s::vector)
                returning id
            """, (row["candidate_name"], row["material_family"], row["summary"],
                  json.dumps(row["candidate"] or {}), json.dumps(row["assay"] or {}),
                  json.dumps(gates), sanitize_for_prompt(approved_by, 80),
                  sanitize_for_prompt(reviewer_note or "", 2000),
                  _vec_literal(embed(f"{row['candidate_name']} {row['summary']}"))))
            new_id = str(cur.fetchone()["id"])
        else:  # delete
            if row["library_id"]:
                cur.execute("delete from validated_library where id = %s::uuid",
                            (row["library_id"],))
            new_id = str(row["library_id"] or "")

        cur.execute("""
            update pending_candidates
            set status = 'approved', reviewer_note = %s, reviewed_at = now()
            where id = %s::uuid
        """, (sanitize_for_prompt(reviewer_note or "", 2000), change_id))
        conn.commit()
    return {"ok": True, "library_id": new_id}


def reject_pending_candidate(change_id: str, reviewer_note: str | None = None) -> bool:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""
            update pending_candidates
            set status = 'rejected', reviewer_note = %s, reviewed_at = now()
            where id = %s::uuid and status = 'pending'
        """, (sanitize_for_prompt(reviewer_note or "", 2000), change_id))
        changed = cur.rowcount
        conn.commit()
    return changed > 0


def cancel_pending_candidate(change_id: str) -> bool:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("delete from pending_candidates where id = %s::uuid and status = 'pending'",
                    (change_id,))
        changed = cur.rowcount
        conn.commit()
    return changed > 0


def get_validated_library(limit: int = 100) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""
            select id, candidate_name, material_family, summary, candidate, assay, gates,
                   approved_by, reviewer_note, created_at
            from validated_library order by created_at desc limit %s
        """, (max(1, min(int(limit), 500)),))
        for row in cur.fetchall():
            try:
                out.append({
                    "id": str(row["id"]), "candidate_name": row["candidate_name"],
                    "material_family": row["material_family"], "summary": row["summary"],
                    "candidate": row["candidate"] or {}, "assay": row["assay"] or {},
                    "gates": row["gates"] or [], "approved_by": row["approved_by"],
                    "reviewer_note": row["reviewer_note"],
                    "created_at": row["created_at"].isoformat()})
            except Exception as e:  # noqa: BLE001
                log.warning("skipping malformed validated_library row: %s", e)
    return out


# ------------------------------------------------------------------ notes & feedback

# Fallback used when Postgres is unreachable. Imported from the agent's own
# notes module so there is exactly one copy of this text in the repo.
def _default_notes() -> dict[str, dict[str, str]]:
    try:
        from server.agent.notes import MATERIAL_NOTES

        return MATERIAL_NOTES
    except Exception:  # noqa: BLE001
        return {}


def get_material_notes(mode: str = "run") -> dict[str, str]:
    """Per-material guidance. Best-effort: falls back to the in-process copy
    so an offline database never breaks the design loop."""
    col = "explain_note" if mode == "explain" else "run_note"
    try:
        with _connect() as conn, conn.cursor() as cur:
            try:
                cur.execute(f"select material, {col} as note from material_notes")  # noqa: S608
            except Exception:  # noqa: BLE001 - table may not exist yet
                conn.rollback()
                return {k: v.get(col, "") for k, v in _default_notes().items()}
            return {r["material"]: r["note"] or "" for r in cur.fetchall()}
    except Exception as e:  # noqa: BLE001
        log.info("material notes from memory (%s)", e)
        return {k: v.get(col, "") for k, v in _default_notes().items()}


def save_feedback(rating: str, success: bool | None, summary: str | None,
                  source: str = "browser") -> bool:
    """Self-healing: creates the table and retries if a fresh database has
    not been migrated."""
    if rating not in ("like", "dislike"):
        return False
    sql = """insert into feedback (rating, success, summary, source)
             values (%s, %s, %s, %s)"""
    args = (rating, success, sanitize_for_prompt(summary or "", 1000), source)
    try:
        with _connect() as conn, conn.cursor() as cur:
            try:
                cur.execute(sql, args)
            except Exception:  # noqa: BLE001
                conn.rollback()
                cur.execute("""
                    create table if not exists feedback (
                        id uuid primary key default gen_random_uuid(),
                        rating text not null,
                        success boolean, summary text,
                        source text not null default 'browser',
                        created_at timestamptz not null default now())
                """)
                cur.execute(sql, args)
            conn.commit()
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("feedback not saved: %s", e)
        return False


def db_health() -> dict[str, Any]:
    """Row counts for /health and the reviewer dashboard."""
    counts: dict[str, Any] = {}
    try:
        with _connect() as conn, conn.cursor() as cur:
            for table in ("enzyme_families", "precedents", "design_runs",
                          "pending_candidates", "validated_library"):
                try:
                    cur.execute(f"select count(*) as n from {table}")  # noqa: S608
                    counts[table] = cur.fetchone()["n"]
                except Exception:  # noqa: BLE001
                    conn.rollback()
                    counts[table] = None
        return {"ok": True, "counts": counts}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "counts": counts}
