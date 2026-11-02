"""Postgres + pgvector client for the shared proposals DB.

Connects to DATABASE_URL (set in .env). Same shape as voodo's
server/db/client.py: embed on write, cosine search on read, and a pending
queue that a human clears.

The rule this module exists to enforce: `proposals` is written by
`approve_pending_change` and by nothing else. The engine cannot put a claim
about biology in front of the next user by itself — a biologist has to say yes
first. Every other function here either fills the queue or reads what came out
of it.
"""
from __future__ import annotations

import functools
import json
import logging
from typing import Any

import psycopg
from psycopg.rows import dict_row

from shared.config import settings
from shared.protocol import (
    Gap,
    PendingChange,
    ProposalMatch,
    ProposalRecord,
    ReviewDecision,
)
from shared.security import clean_pmids, sanitize_for_prompt

log = logging.getLogger("shrapmind.db")

_ALLOWED_CHANGE_TYPES = {"add", "delete", "amend"}
_ALLOWED_VERDICTS = {
    "agree", "disagree", "unconvinced", "needs_experiment", "out_of_scope"
}

# Approving a proposal records that a qualified person believed it. It does not
# record that anyone measured it, so review never promotes a row to
# 'experimental'. See the note at the top of schema.sql.
_REVIEW_EVIDENCE_LEVEL = "expert_review"

EMBED_DIM = 384


# ── Embeddings ───────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def _embedder() -> tuple[Any, str]:
    """The sentence-transformer if it is installed, else a lexical stand-in.

    voodo assumes all-MiniLM-L6-v2 is present. Here it may not be, and the
    choice matters enough to surface rather than hide: a lexical embedder
    matches shared vocabulary, so it will connect "fibrotic capsule" to
    "fibrous capsule formation" and will not connect "foreign body response"
    to "implant encapsulation". Both are 384-wide, so the schema and the
    stored vectors stay compatible, but a mixed corpus is meaningless —
    re-seed after installing the model rather than topping up.
    """
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(settings.embedding_model), "semantic"
    except Exception:  # noqa: BLE001 — absence is expected, not exceptional
        log.warning(
            "sentence-transformers not installed; using the lexical embedder. "
            "Retrieval matches wording, not meaning. Install it and re-run "
            "`python -m server.db.seed --reset` for semantic search."
        )
        return _LexicalEmbedder(), "lexical"


class _LexicalEmbedder:
    """Deterministic hashed n-gram vectors, 384-wide, L2 normalised.

    No training and no model file, so it behaves identically on every machine.
    Character 4-grams inside long words are what let morphological variants
    (hydrolase/hydrolases, fibrotic/fibrosis) land near each other without a
    stemmer whose rules would be one more thing to get wrong on scientific
    vocabulary.
    """

    import re as _re

    _WORD = _re.compile(r"[a-z0-9][a-z0-9\-']*")
    _STOP = frozenset("""
    a an and are as at be been but by for from had has have in into is it its
    of on or that the their then there these this to was were which with we
    our using used use show shows shown study studies results result here
    """.split())

    def encode(self, text: str, normalize_embeddings: bool = True) -> list[float]:
        import hashlib
        import math
        import unicodedata
        from collections import Counter

        import numpy as np

        words = [
            w for w in self._WORD.findall(
                unicodedata.normalize("NFKD", text or "").lower()
            )
            if w not in self._STOP and len(w) > 1
        ]
        feats: Counter[str] = Counter()
        for w in words:
            feats[f"w:{w}"] += 1
            if len(w) >= 7:
                for i in range(len(w) - 3):
                    feats[f"c:{w[i:i + 4]}"] += 1
        for a, b in zip(words, words[1:]):
            feats[f"b:{a}_{b}"] += 1

        vec = np.zeros(EMBED_DIM, dtype=np.float32)
        for feature, count in feats.items():
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            n = int.from_bytes(digest, "big")
            # The sign is the standard hashing trick: without it collisions
            # only ever add, and unrelated documents drift together as the
            # corpus grows.
            sign = 1.0 if (n >> 63) & 1 else -1.0
            # Sublinear TF — a word used twenty times is not twenty times the
            # evidence, and long abstracts should not win on repetition.
            vec[n % EMBED_DIM] += sign * (1.0 + math.log(count))

        norm = float(np.linalg.norm(vec))
        return (vec / norm).tolist() if norm else [0.0] * EMBED_DIM


def embed(text: str) -> list[float]:
    model, _ = _embedder()
    vec = model.encode(text or "", normalize_embeddings=True)
    return [float(x) for x in (vec.tolist() if hasattr(vec, "tolist") else vec)]


def embedding_kind() -> str:
    """'semantic' or 'lexical' — shown in the dashboard so a reviewer reading
    a 'similar case' knows what kind of similar."""
    return _embedder()[1]


# ── Connection helpers ───────────────────────────────────────────────────────

def _connect() -> psycopg.Connection:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL not set in .env")
    return psycopg.connect(
        settings.database_url, row_factory=dict_row, connect_timeout=5
    )


def _vec_literal(vec: list[float]) -> str:
    """pgvector accepts the textual form '[v1,v2,...]'."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def _gaps(raw: Any) -> list[Gap]:
    items = raw if isinstance(raw, list) else json.loads(raw or "[]")
    out: list[Gap] = []
    for g in items:
        if isinstance(g, dict):
            try:
                out.append(Gap(**g))
            except Exception as err:  # noqa: BLE001
                log.warning("dropping malformed gap (%s)", err)
    return out


# ── Reading what has been approved ───────────────────────────────────────────

def search_similar(description: str, top_k: int = 3) -> list[ProposalMatch]:
    """Vector similarity search via cosine distance (`<=>`)."""
    q = _vec_literal(embed(description))
    sql = """
        select id::text as id, problem_summary, material, enzyme_name,
               uniprot_accession, score, rationale, gaps, evidence_level,
               substrate_class,
               1 - (embedding <=> %s::vector) as similarity
        from proposals
        where embedding is not null
        order by embedding <=> %s::vector
        limit %s
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (q, q, top_k))
        rows: list[dict[str, Any]] = cur.fetchall()

    return [
        ProposalMatch(
            record=ProposalRecord(
                id=r["id"],
                problem_summary=r["problem_summary"],
                material=r["material"],
                enzyme_name=r["enzyme_name"],
                uniprot_accession=r["uniprot_accession"],
                score=r["score"],
                rationale=r["rationale"],
                gaps=_gaps(r["gaps"]),
                evidence_level=r["evidence_level"],
                substrate_class=r["substrate_class"],
            ),
            score=float(r["similarity"]),
        )
        for r in rows
    ]


def get_proposal(proposal_id: str) -> ProposalRecord | None:
    sql = """
        select id::text as id, problem_summary, material, enzyme_name,
               uniprot_accession, score, rationale, gaps, evidence_level,
               substrate_class
        from proposals where id = %s
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (proposal_id,))
        r = cur.fetchone()
    if not r:
        return None
    return ProposalRecord(
        id=r["id"], problem_summary=r["problem_summary"], material=r["material"],
        enzyme_name=r["enzyme_name"], uniprot_accession=r["uniprot_accession"],
        score=r["score"], rationale=r["rationale"], gaps=_gaps(r["gaps"]),
        evidence_level=r["evidence_level"], substrate_class=r["substrate_class"],
    )


def get_all_proposals(limit: int = 100) -> list[ProposalRecord]:
    """List recent proposals, skipping rows too malformed to build.

    One bad `gaps` blob used to take the whole dashboard down with a 500; now
    it costs that row and a log line.
    """
    sql = """
        select id::text as id, problem_summary, material, enzyme_name,
               uniprot_accession, score, rationale, gaps, evidence_level,
               substrate_class
        from proposals order by created_at desc limit %s
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (limit,))
        rows = cur.fetchall()

    out, skipped = [], 0
    for r in rows:
        try:
            out.append(ProposalRecord(
                id=r["id"], problem_summary=r["problem_summary"] or "",
                material=r["material"] or "", enzyme_name=r["enzyme_name"],
                uniprot_accession=r["uniprot_accession"], score=r["score"],
                rationale=r["rationale"], gaps=_gaps(r["gaps"]),
                evidence_level=r["evidence_level"] or "curated",
                substrate_class=r["substrate_class"],
            ))
        except Exception as err:  # noqa: BLE001
            skipped += 1
            log.warning("skipping malformed proposal %s (%s)", r.get("id"), err)
    if skipped:
        log.warning("get_all_proposals: skipped %d malformed row(s)", skipped)
    return out


# ── The review queue ─────────────────────────────────────────────────────────

def submit_pending_change(
    change_type: str,
    problem_summary: str,
    reason: str,
    material: str | None = None,
    enzyme_name: str | None = None,
    rationale: str | None = None,
    gaps: list[Gap] | None = None,
    submitted_by: str = "engine",
    proposal_id: str | None = None,
) -> PendingChange:
    """Queue an assertion for a biologist.

    Everything written here is rendered in the dashboard and, once approved,
    embedded and served as context to later runs. So sanitize every text field
    regardless of who submitted it — the engine, a reviewer, or some future
    caller nobody has written yet. This is the chokepoint.
    """
    if change_type not in _ALLOWED_CHANGE_TYPES:
        raise ValueError(f"submit_pending_change: invalid type {change_type!r}")

    safe_problem = sanitize_for_prompt(problem_summary or "", max_len=300)
    safe_reason = sanitize_for_prompt(reason or "", max_len=300)
    safe_rationale = sanitize_for_prompt(rationale or "", max_len=800) if rationale else None
    safe_material = sanitize_for_prompt(material or "", max_len=40) or None
    safe_enzyme = sanitize_for_prompt(enzyme_name or "", max_len=80) or None
    safe_by = sanitize_for_prompt(submitted_by or "", max_len=64)
    gaps_json = json.dumps([g.model_dump() for g in (gaps or [])])

    sql = """
        insert into pending_changes
            (type, proposal_id, problem_summary, material, enzyme_name,
             rationale, gaps, reason, submitted_by)
        values (%s, %s::uuid, %s, %s, %s, %s, %s::jsonb, %s, %s)
        returning id::text, created_at::text
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (
            change_type, proposal_id, safe_problem, safe_material, safe_enzyme,
            safe_rationale, gaps_json, safe_reason, safe_by,
        ))
        row = cur.fetchone()
        conn.commit()

    return PendingChange(
        id=row["id"], type=change_type, proposal_id=proposal_id,
        problem_summary=safe_problem, material=safe_material,
        enzyme_name=safe_enzyme, rationale=safe_rationale,
        gaps=gaps or [], reason=safe_reason, submitted_by=safe_by,
        status="pending", created_at=str(row["created_at"]),
    )


def get_pending_changes(status: str | None = None) -> list[dict]:
    base = """
        select id::text, type, proposal_id::text, problem_summary, material,
               enzyme_name, rationale, gaps, reason, submitted_by, status,
               verdict, confidence, reviewer, reviewer_note, cites_pmid,
               created_at::text, reviewed_at::text
        from pending_changes
    """
    if status:
        sql, params = base + " where status = %s order by created_at desc", (status,)
    else:
        sql, params = base + " order by created_at desc", ()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def approve_pending_change(change_id: str, decision: ReviewDecision) -> bool:
    """Accept a queued assertion and write it into `proposals`.

    The approved row is stored at `expert_review`, never higher. A biologist
    agreeing that an enzyme is the right choice is a considered opinion about
    the published evidence; it adds no measurement, and a schema that let
    approval mint `experimental` rows would quietly turn consensus into data.
    """
    if decision.verdict not in _ALLOWED_VERDICTS:
        raise ValueError(f"approve_pending_change: invalid verdict {decision.verdict!r}")

    sql_get = """
        select type, proposal_id::text, problem_summary, material, enzyme_name,
               rationale, gaps
        from pending_changes
        where id = %s and status = 'pending'
    """
    note = sanitize_for_prompt(decision.note or "", max_len=2000)
    reviewer = sanitize_for_prompt(decision.reviewer or "", max_len=64)
    pmids = clean_pmids(decision.cites_pmid)

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql_get, (change_id,))
        row = cur.fetchone()
        if not row:
            return False

        if row["type"] in ("add", "amend"):
            gaps_json = json.dumps(
                row["gaps"] if isinstance(row["gaps"], list)
                else json.loads(row["gaps"] or "[]")
            )
            cur.execute(
                """
                insert into proposals
                    (problem_summary, material, enzyme_name, rationale, gaps,
                     evidence_level, embedding)
                values (%s, %s, %s, %s, %s::jsonb, %s, %s::vector)
                """,
                (
                    row["problem_summary"], row["material"] or "unknown",
                    row["enzyme_name"], row["rationale"], gaps_json,
                    _REVIEW_EVIDENCE_LEVEL,
                    _vec_literal(embed(row["problem_summary"])),
                ),
            )
        elif row["type"] == "delete" and row["proposal_id"]:
            cur.execute("delete from proposals where id = %s", (row["proposal_id"],))

        cur.execute(
            """
            update pending_changes
            set status = 'approved', verdict = %s, confidence = %s,
                reviewer = %s, reviewer_note = %s, cites_pmid = %s,
                reviewed_at = now()
            where id = %s
            """,
            (decision.verdict, decision.confidence, reviewer, note, pmids, change_id),
        )
        _insert_review_note(cur, change_id, reviewer, note)
        conn.commit()
    return True


def reject_pending_change(change_id: str, decision: ReviewDecision) -> bool:
    """Turn a queued assertion down. Nothing is written to `proposals`."""
    if decision.verdict not in _ALLOWED_VERDICTS:
        raise ValueError(f"reject_pending_change: invalid verdict {decision.verdict!r}")
    note = sanitize_for_prompt(decision.note or "", max_len=2000)
    reviewer = sanitize_for_prompt(decision.reviewer or "", max_len=64)
    pmids = clean_pmids(decision.cites_pmid)

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            update pending_changes
            set status = 'rejected', verdict = %s, confidence = %s,
                reviewer = %s, reviewer_note = %s, cites_pmid = %s,
                reviewed_at = now()
            where id = %s and status = 'pending'
            """,
            (decision.verdict, decision.confidence, reviewer, note, pmids, change_id),
        )
        affected = cur.rowcount
        if affected:
            _insert_review_note(cur, change_id, reviewer, note)
        conn.commit()
    return affected > 0


def _insert_review_note(cur, change_id: str, reviewer: str, note: str) -> None:
    """Store and embed the reasoning, which is the part worth searching."""
    if not note:
        return
    cur.execute(
        """
        insert into review_notes (change_id, reviewer, note, embedding)
        values (%s, %s, %s, %s::vector)
        """,
        (change_id, reviewer or "unknown", note, _vec_literal(embed(note))),
    )


def search_review_notes(text: str, top_k: int = 5) -> list[dict]:
    """Find objections already raised, so two reviewers do not spend an hour
    each arriving at the same one independently."""
    q = _vec_literal(embed(text))
    sql = """
        select n.id::text as id, n.reviewer, n.note, n.created_at::text,
               c.problem_summary, c.verdict,
               1 - (n.embedding <=> %s::vector) as similarity
        from review_notes n
        left join pending_changes c on c.id = n.change_id
        where n.embedding is not null
        order by n.embedding <=> %s::vector
        limit %s
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (q, q, top_k))
        return [dict(r) for r in cur.fetchall()]


def open_experiments() -> list[dict]:
    """What reviewers said needs a bench, most-corroborated first."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("select * from open_experiments")
        return [dict(r) for r in cur.fetchall()]


# ── Lightweight feedback ─────────────────────────────────────────────────────

def save_feedback(
    rating: str, proposal_id: str | None = None,
    summary: str | None = None, source: str = "browser",
) -> bool:
    """Record a 👍/👎 on a proposal, independent of the score the engine set."""
    if rating not in ("like", "dislike"):
        return False
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into feedback (rating, proposal_id, summary, source)
                values (%s, %s::uuid, %s, %s)
                """,
                (rating, proposal_id, (summary or "")[:2000], source),
            )
            conn.commit()
        return True
    except Exception as err:  # noqa: BLE001
        log.warning("save_feedback failed: %s", err)
        return False


_MATERIAL_ALIASES_DEFAULT: dict[str, str] = {
    "polyester": "PET", "dacron": "PET", "nylon": "PA",
    "polyamide": "PA", "polyurethane": "PUR", "rubber": "NR",
}


def get_material_aliases() -> dict[str, str]:
    """Free-text material name → the key the engine knows.

    Falls back to in-memory defaults if the DB is unreachable, so a dead
    Postgres degrades lookup rather than breaking it.
    """
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("select alias, canonical from material_aliases")
            return {r["alias"]: r["canonical"] for r in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return dict(_MATERIAL_ALIASES_DEFAULT)
