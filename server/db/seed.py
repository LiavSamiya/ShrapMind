"""Fill the review queue from the engine.

Runs f2c over every material it covers and queues each decision for a
biologist. Nothing lands in `proposals`: the queue is the point, and an empty
`proposals` table on a fresh install is the correct state — it means no human
has agreed to anything yet.

    python -m server.db.seed            # queue what is not already queued
    python -m server.db.seed --reset    # clear everything first

`--reset` exists mainly for swapping the embedder. Vectors from the lexical
stand-in and from a sentence transformer are not comparable, so a corpus
holding both returns nonsense; re-seed rather than top up.
"""
from __future__ import annotations

import argparse
import sys

from f2c import warehouse
from f2c.engine import decide
from f2c.schema import MaterialSpec
from server.db import client
from shared.protocol import Gap

# The case every material is queued under. Deep muscle is the only site the
# engine covers, and the numbers are the ones the worked example uses, so a
# reviewer sees a concrete case rather than an abstraction.
MASS_MG = 50.0
CRYSTALLINITY_PCT = 55.0
PARTICLE_SIZE_MM = 0.8


def _summary(material: str) -> str:
    return (
        f"{material} fragment, {MASS_MG:g} mg, {CRYSTALLINITY_PCT:g}% crystalline, "
        f"{PARTICLE_SIZE_MM:g} mm particles, deep skeletal muscle"
    )


def seed(reset: bool = False) -> int:
    proteins = warehouse.load()
    materials = sorted({
        (s.get("abbreviation") or "").strip()
        for p in proteins for s in (p.substrates or [])
        if isinstance(s, dict) and s.get("abbreviation")
    })
    if not materials:
        print("no materials in the warehouse; nothing to seed", file=sys.stderr)
        return 1

    with client._connect() as conn, conn.cursor() as cur:
        if reset:
            cur.execute("truncate review_notes, feedback, pending_changes, proposals "
                        "restart identity cascade")
            conn.commit()
            print("cleared proposals, pending_changes, review_notes, feedback")
        cur.execute("select problem_summary from pending_changes")
        already = {r["problem_summary"] for r in cur.fetchall()}

    queued = skipped = 0
    for material in materials:
        summary = _summary(material)
        if summary in already:
            skipped += 1
            continue

        spec = MaterialSpec(
            polymer=material, mass_mg=MASS_MG,
            crystallinity_pct=CRYSTALLINITY_PCT,
            particle_size_mm=PARTICLE_SIZE_MM,
        )
        decision = decide(spec, proteins)
        chosen = decision.selected

        gaps = [
            Gap(kind=g.kind, detail=g.detail, measured=g.measured,
                target=g.target, action=g.engineering_target,
                pmid=(g.evidence.pmid if g.evidence else None))
            for g in (chosen.gaps if chosen else [])
        ]

        client.submit_pending_change(
            change_type="add",
            problem_summary=summary,
            material=material,
            enzyme_name=chosen.protein.name if chosen else None,
            rationale=decision.rationale,
            gaps=gaps,
            reason=(
                f"Engine verdict: {decision.verdict}. Queued for review before "
                "any of it is presented as settled."
            ),
            submitted_by="engine",
        )
        queued += 1
        label = chosen.protein.name if chosen else f"({decision.verdict})"
        print(f"  queued {material:5s} -> {label}")

    print(f"\nqueued {queued}, already present {skipped}")
    print(f"embedder: {client.embedding_kind()}")
    print("proposals table stays empty until a biologist approves something.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reset", action="store_true",
                    help="clear all rows before seeding")
    args = ap.parse_args()
    return seed(reset=args.reset)


if __name__ == "__main__":
    sys.exit(main())
