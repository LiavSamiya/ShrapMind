"""Which arm of this project is live, and which is history.

The project began on polymer fragments and moved to metals. Both bodies of
work are real and neither was discarded, but only one is being developed --
and a reader who cannot tell them apart will take a polymer finding for a
current one. That has already happened once here: a full bench protocol was
written around a PET cutinase after the decision to focus on metals, correct
work aimed at the wrong arm.

So the distinction is held as data rather than as a note in a page. Every
material the engine knows carries an arm, the active arm is named once, and
the interface reads it instead of deciding for itself.
"""
from __future__ import annotations

from typing import Any

METAL = "metal"
POLYMER = "polymer"
# Glass, ceramic, silica and stone are neither, and they are not the earlier
# direction either: a surgeon asking whether a glass fragment is treatable is
# asking a current question, and the answer -- no pathway, for chemical
# reasons -- is part of what the product has to say.
MINERAL = "mineral"

ACTIVE_ARM = METAL

DECIDED_ON = "2026-10-31"
DECISION = (
    "The team decided to focus the product on metals. Polymer work stays in "
    "the repository and stays published, as an earlier direction -- it is not "
    "deleted, because the evidence discipline it established is what the "
    "metal arm runs on, and because a finding does not stop being true when "
    "the project moves."
)

# Materials belonging to the earlier arm. Everything else the engine knows is
# a metal or a mineral and belongs to the current one.
POLYMER_MATERIALS = frozenset({
    "PET", "PA", "PLA", "PHA", "PBS", "PEF", "PC", "PUR", "PBAT", "NR",
    "PE", "PP", "PS", "PVC",
})
MINERAL_MATERIALS = frozenset({"glass", "ceramic", "silica", "stone"})


def arm(material: str) -> str:
    """Which arm a material belongs to."""
    if material in POLYMER_MATERIALS:
        return POLYMER
    if material in MINERAL_MATERIALS:
        return MINERAL
    return METAL


def is_active(material: str) -> bool:
    """Whether this material is in current scope.

    Minerals count as active even though nothing can be done for them: the
    refusal is a current answer to a current question. Only the polymer arm
    is history.
    """
    return arm(material) != POLYMER


def banner(lang: str = "en") -> dict[str, Any]:
    """What a page should say above anything from the earlier arm."""
    if lang == "he":
        return {
            "label": "כיוון קודם",
            "title": "זו עבודת הפולימרים, לא המוצר הנוכחי",
            "body": (
                "הפרויקט התמקד במתכות. הדף הזה נשמר כי הממצאים בו נכונים "
                "והמשמעת הראייתית שהוא ביסס היא מה שזרוע המתכות רצה עליו — "
                "אבל שום דבר כאן אינו תיאור של המוצר הנוכחי."
            ),
        }
    return {
        "label": "earlier direction",
        "title": "This is the polymer work, not the current product",
        "body": (
            "The project focused on metals. This page is kept because its "
            "findings hold and because the evidence discipline it "
            "established is what the metal arm runs on -- but nothing here "
            "describes the current product."
        ),
    }


def summary() -> dict[str, Any]:
    return {
        "active_arm": ACTIVE_ARM,
        "decided_on": DECIDED_ON,
        "decision": DECISION,
        "polymer_materials": sorted(POLYMER_MATERIALS),
        "mineral_materials": sorted(MINERAL_MATERIALS),
        "why_kept": (
            "Nothing is deleted. The polymer arm is where the substrate "
            "classification, the catalytic-evidence signal and the "
            "host-safety screen were built, and all three now serve the "
            "metal arm."
        ),
    }
