"""What success means for a fragment, and how far the evidence reaches for it.

The engine spent its first version answering one question: can an enzyme
consume this fragment. That is the hardest form of the question and it is
usually not the clinical one. The problem being solved is removal that beats
surgery, and surgery loses on other grounds than completeness:

  debulk  A fragment pressing on a nerve forces an urgent approach through
          tissue the surgeon would rather not cross. Taking a fifth of it away
          relieves the pressure and buys an elective operation under better
          conditions. Completeness is irrelevant to that benefit.

  micro   Dozens of fragments below a millimetre cannot be found one by one.
          Surgery scales badly with count; surface chemistry does not care how
          many pieces the same mass is in, and in fact prefers it divided.

Two consequences fall out of the arithmetic rather than out of optimism, and
both are computed here rather than asserted. The crystalline ceiling that
blocks full degradation does not block a 20% target until crystallinity passes
80%. And specific surface area, which is what surface erosion scales with,
rises steeply as fragments get smaller -- so the many-tiny-fragments case is
the favourable one, not the difficult one.

One assumption does not survive contact with the literature, and it is called
out here because it would otherwise be load-bearing: the idea that a debulked
fragment drifts away from the nerve on its own. Fragment migration is real and
well documented, and the documented mechanism is embolisation through the
vasculature.
"""
from __future__ import annotations

from typing import Any

FULL, DEBULK, MICRO = "full", "debulk", "micro"

# Above this, the amorphous fraction is too small to supply even a partial
# target. Below it, the ceiling that blocks full degradation says nothing
# about a partial one.
MAX_USEFUL_CRYSTALLINITY_PCT = 80.0

# A fragment is "micro" below this. Chosen because it is roughly where
# individual retrieval stops being practical and the count starts to dominate
# the operative time.
MICRO_SIZE_MM = 0.5

LABEL = {
    FULL: "consume the fragment entirely",
    DEBULK: "remove part of it, to relieve pressure and defer surgery",
    MICRO: "clear many fragments too small to retrieve individually",
}


def _ceiling(crystallinity_pct: float | None, target_pct: float) -> dict[str, Any]:
    """Does the crystalline fraction leave room for the target?

    Enzymes act on amorphous regions, so the amorphous fraction is the upper
    bound on what can be removed at all. For a full target that bound binds
    immediately; for a partial one it binds only when the amorphous fraction
    falls below the target.
    """
    if crystallinity_pct is None:
        return {
            "known": False,
            "note": "Crystallinity is not characterised, so the ceiling cannot "
                    "be checked. It is the first thing to measure on a real "
                    "fragment.",
        }
    amorphous = 100.0 - crystallinity_pct
    return {
        "known": True,
        "crystallinity_pct": crystallinity_pct,
        "amorphous_pct": round(amorphous, 1),
        "target_pct": target_pct,
        "headroom_pct": round(amorphous - target_pct, 1),
        "blocks": amorphous < target_pct,
        "note": (
            f"{amorphous:.0f}% of this fragment is amorphous and therefore "
            f"reachable. A {target_pct:.0f}% target leaves "
            f"{amorphous - target_pct:.0f} points of headroom."
            if amorphous >= target_pct else
            f"Only {amorphous:.0f}% is amorphous, which is less than the "
            f"{target_pct:.0f}% asked for. The target cannot be met by surface "
            "erosion regardless of how long the enzyme is given."
        ),
    }


def assess(
    goal: str,
    crystallinity_pct: float | None,
    particle_size_mm: float | None,
    debulk_target_pct: float = 20.0,
    specific_area_mm2_per_mg: float | None = None,
) -> dict[str, Any]:
    """How far the evidence reaches for this goal, with the arithmetic shown."""
    goal = goal if goal in (FULL, DEBULK, MICRO) else FULL
    # Only debulking lowers the completeness bar. Clearing micro fragments
    # still means clearing them, so it faces the same crystalline ceiling as
    # full degradation -- what it changes is the rate, through surface area,
    # and conflating the two would hand the mode a feasibility it has not got.
    target = debulk_target_pct if goal == DEBULK else 100.0
    out: dict[str, Any] = {
        "goal": goal,
        "means": LABEL[goal],
        "target_pct": target,
        "ceiling": _ceiling(crystallinity_pct, target),
        "warnings": [],
        "notes": [],
    }

    if goal == DEBULK:
        out["notes"].append(
            "The clinical benefit here does not require the fragment to be "
            "gone. Relieving pressure converts an urgent approach through "
            "tissue the surgeon would rather not cross into an elective one, "
            "and a smaller fragment needs a narrower corridor to reach."
        )
        # The dangerous version of the same idea, named so it cannot be
        # assumed quietly.
        out["warnings"].append({
            "claim": "A debulked fragment drifts away from the nerve, so "
                     "surgery becomes safe later.",
            "status": "contradicted by the migration literature",
            "detail": (
                "Fragment migration is well documented and the documented "
                "mechanism is embolisation through the vasculature -- in one "
                "report a cranial fragment reached the right ventricle within "
                "18 minutes. A fragment beside a vessel that is made smaller "
                "and lighter is a candidate for exactly that. Plan the benefit "
                "around the material removed, not around the fragment moving."
            ),
        })

    if goal == MICRO:
        out["notes"].append(
            "Surgery scales badly with fragment count: each piece must be "
            "found. Surface erosion does not care how many pieces the mass is "
            "divided into, and prefers it divided, because it scales with area."
        )
        if specific_area_mm2_per_mg:
            out["surface_advantage"] = {
                "specific_area_mm2_per_mg": specific_area_mm2_per_mg,
                "note": (
                    "Specific surface area rises steeply as fragments get "
                    "smaller, so the same mass in smaller pieces presents more "
                    "of itself to the enzyme. This is the one place where the "
                    "fragment's own geometry works in favour of the approach."
                ),
            }
        if particle_size_mm is not None and particle_size_mm > MICRO_SIZE_MM:
            out["warnings"].append({
                "claim": f"These fragments are in the micro regime.",
                "status": "does not match the input",
                "detail": (
                    f"{particle_size_mm:g} mm is above the {MICRO_SIZE_MM:g} mm "
                    "threshold this mode assumes. At that size individual "
                    "retrieval is still practical, so the comparison against "
                    "surgery is not the one this mode makes."
                ),
            })

    # True for every goal, and the reason none of this is a feasibility claim.
    out["rate_unknown"] = (
        "What the arithmetic settles is how much can be removed, not how "
        "fast. No interfacial rate has been measured on a solid at 37 C, so "
        "none of these modes carries a duration. That measurement is the gate."
    )
    return out
