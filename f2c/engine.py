"""Orchestration: material in, decision out."""
from __future__ import annotations

import datetime as _dt

from .formulate import capture_requirement
from .rank import rank
from .retrieve import retrieve
from .schema import Decision, MaterialSpec, Protein

# A candidate below this carries so little evidence that presenting it as "the
# enzyme" would overstate what is known.
MIN_SCORE = 0.25


def decide(
    material: MaterialSpec, proteins: list[Protein], max_alternatives: int = 4
) -> Decision:
    now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    result = retrieve(material, proteins)

    if result.blocked_reason:
        return Decision(
            material=material,
            verdict="no_pathway",
            selected=None,
            alternatives=[],
            rationale=result.blocked_reason,
            generated_at=now,
        )

    if not result.candidates:
        extra = ""
        if result.oligomer_only_excluded:
            extra = (
                f" {result.oligomer_only_excluded} entr"
                f"{'ies were' if result.oligomer_only_excluded != 1 else 'y was'} "
                "excluded because activity was shown only on soluble oligomers, "
                "which does not demonstrate erosion of a solid fragment."
            )
        return Decision(
            material=material,
            verdict="no_pathway",
            selected=None,
            alternatives=[],
            rationale=(
                f"No enzyme with demonstrated activity on {result.material_key} is "
                f"present in the seed set.{extra} This is a statement about available "
                "evidence, not a claim that the material is indegradable."
            ),
            generated_at=now,
        )

    scored = rank(result.candidates)
    best = scored[0]

    if best.score < MIN_SCORE:
        return Decision(
            material=material,
            verdict="no_candidate_meets_bar",
            selected=None,
            alternatives=scored[:max_alternatives],
            rationale=(
                f"{len(scored)} enzymes act on {result.material_key}, but the best "
                f"scores {best.score:.2f}, below the {MIN_SCORE:.2f} bar. The "
                "candidates are listed so the gaps can be closed rather than hidden."
            ),
            generated_at=now,
        )

    return Decision(
        material=material,
        verdict="enzyme_selected",
        selected=best,
        alternatives=scored[1 : 1 + max_alternatives],
        rationale=(
            f"Selected from {len(scored)} enzymes with demonstrated activity on "
            f"{result.material_key}, ranked on evidence strength and fit to body "
            "conditions."
        ),
        capture=capture_requirement(result.material_key, material.mass_mg),
        generated_at=now,
    )
