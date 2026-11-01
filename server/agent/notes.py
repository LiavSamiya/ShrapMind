"""Per-material guidance, retrieved lazily by the `get_material_notes` tool.

Retrieval instead of prompt bloat: the system prompt stays small and the
agent pulls the notes for the one material family it is actually working on.
The same trick as a tool that fetches per-topic instructions - it keeps the
cached prefix stable and stops the model from reading four irrelevant
material briefs on every turn.

This module is the single source of this text. server/db/seed.py imports it
to load `material_notes`, and server/db/client.get_material_notes() falls
back to it when Postgres is unreachable. One copy, three consumers.

Each note is written to do one job: tell the model what the rate limit
actually is for this material, and what would make a confident answer wrong.
"""
from __future__ import annotations

MATERIAL_NOTES: dict[str, dict[str, str]] = {
    "cellulose": {
        "run_note": (
            "Wood / cellulose is the flagship route and the one with the cleanest "
            "story: beta-1,4-glycosidic hydrolysis to cellobiose and glucose, both "
            "ordinary metabolites, so the product-toxicity question is largely "
            "answered before you start. The rate limit is ACCESSIBILITY, not "
            "turnover: crystalline regions and lignin shielding mean most of the "
            "mass is not exposed, so a high k_cat on soluble substrate predicts "
            "very little. Expect accessibility 0.2-0.4 for seasoned timber. "
            "Two things will make a confident answer wrong here: assuming the "
            "fragment is sterile (it is not - a wood splinter carries soil and "
            "bacteria, and biofilm blocks the surface you are trying to reach), "
            "and reporting a rate measured on milled powder as if it applied to a "
            "solid splinter."
        ),
        "explain_note": (
            "Cellulose is where this approach is most defensible: the chemistry is "
            "ordinary hydrolysis, the products are sugars, and cellulases are "
            "industrially routine. Explain that the hard part is reaching the "
            "bonds, not breaking them."
        ),
    },
    "pet": {
        "run_note": (
            "PET / polyester has strong published enzyme precedent, but read the "
            "conditions before you quote a number: nearly all of it is at 50-70 "
            "degC on amorphous film, and this application is 37 degC on "
            "semi-crystalline fibre in serum. That gap is the whole research "
            "question, not a detail. Carry the measured conditions through to the "
            "report. Products are MHET, terephthalic acid and ethylene glycol - "
            "ethylene glycol is the one to bound explicitly rather than wave past, "
            "and the capture gate exists mostly for it. Degree of crystallinity "
            "dominates the achievable rate."
        ),
        "explain_note": (
            "PET is the benchmark route: good enough precedent to prove the design "
            "loop works, with an honest gap between published assay temperature "
            "and body temperature that the project has to close."
        ),
    },
    "cotton": {
        "run_note": (
            "Cotton is the same chemistry as cellulose with far higher "
            "crystallinity, so treat accessibility as the binding constraint "
            "(0.15-0.3). The additional risk is not the polymer: it is the dyes "
            "and finishes, which are an additive load the product-toxicity gate "
            "has to account for. A clean result on undyed cotton says nothing "
            "about dyed fabric."
        ),
        "explain_note": (
            "Cotton behaves like cellulose but slower, and the textile chemistry "
            "that comes with it is a separate risk from the fibre itself."
        ),
    },
    "iron_steel": {
        "run_note": (
            "Iron / steel is the highest-risk route and the project's own concept "
            "brief flags it as such. Enzyme-assisted corrosion is documented but "
            "slow, and it is limited by oxygen availability and by passivation - "
            "the oxide layer that forms is the thing standing between you and the "
            "metal. Critically, the reaction liberates IONS, not metabolites, so "
            "CAPTURE is the binding constraint, not rate: a fast route that leaks "
            "free iron is worse than a slow one that does not. If the capture "
            "gate fails here, the answer is no-go, not 'optimise the enzyme'. "
            "Do not present this route as near-term."
        ),
        "explain_note": (
            "Metal is the long-horizon vision, not the first product. The reason "
            "is specific: the reaction releases metal ions, so the hydrogel's "
            "ability to hold them - not the enzyme's speed - decides whether it "
            "is safe."
        ),
    },
    "polyurethane": {
        "run_note": (
            "Polyurethane hydrolysis is a research route with one hard blocker: "
            "aromatic amine release. A route that cannot demonstrate amine-free "
            "products must not advance, regardless of how good its erosion rate "
            "looks. Treat the product panel as the gate, not the kinetics."
        ),
        "explain_note": (
            "Polyurethane is gated on what it releases rather than how fast it "
            "degrades - the breakdown products are the problem."
        ),
    },
    "unknown": {
        "run_note": (
            "The material family was not identified. Do not design against a "
            "guess. The correct output is a request for material identification - "
            "a sample, or spectroscopy - and an explicit statement that no "
            "catalyst can be selected without it. 'Probably plastic' is not a "
            "specification; the chemistry, the products and the gates all differ "
            "between families."
        ),
        "explain_note": (
            "Without knowing what the fragment is made of there is no reaction to "
            "design for. Say so plainly rather than offering a generic answer."
        ),
    },
}


def get_notes(material: str, mode: str = "run") -> str:
    """Substring match onto a material family, like the per-topic instruction
    retrieval it is modelled on. Falls back to an explicit 'identify first'
    answer rather than to generic advice."""
    key = "explain_note" if mode == "explain" else "run_note"
    m = (material or "").lower()
    for family, notes in MATERIAL_NOTES.items():
        if family in m or any(part in m for part in family.split("_")):
            return notes[key]
    return MATERIAL_NOTES["unknown"][key]
