"""Screen the enzyme, separately from the reaction.

The gate battery asks whether the bond class being attacked occurs in human
tissue. For polylactide the answer is no: PLA hydrolysis is aliphatic-ester
chemistry and human structural protein is held together by peptide bonds. On
that question every protease in the warehouse passes.

But the question was asked about the *reaction specification*, not about the
*protein*. The peptidases in the warehouse are retrieved as PLA candidates,
and their own catalytic activity is on peptide bonds -- which is what collagen,
elastin, fibronectin and laminin are made of. An enzyme that digests the tissue
holding the wound together is worse than leaving the fragment in place.

This module existed as prose on the safety review page before it existed as
code. That page stated the screen was "now a gate" and that "host-unsafe
candidates sort last at retrieval"; neither was true, because nothing in
rank.py knew about host substrates. Writing it down is what makes the claim
true, and makes the three pages one mechanism instead of three assertions.

Two rules the whole module turns on:

1. **Severity is graded, not binary.** A screen that blocked everything would
   be useless. Loss of structural integrity is not the same as local
   irritation, so the classes carry what is at risk and what follows.

2. **No flag is not a clean bill of health.** Most of the warehouse has never
   been tested against human tissue. Reporting those as "safe" would be
   inventing a result, so the absence of a flag is reported as an absence and
   `is_screened` stays False.
"""
from __future__ import annotations

from typing import Any, Iterable

BLOCKING = "blocking"
SERIOUS = "serious"
CAUTION = "caution"
UNFLAGGED = "unflagged"

# Worst first, which is also the order candidates sort in.
SEVERITY_ORDER = (BLOCKING, SERIOUS, CAUTION, UNFLAGGED)
_RANK = {s: i for i, s in enumerate(SEVERITY_ORDER)}

# EC prefixes, longest match wins so 3.1.1.3 beats 3.1.1.
EC_CLASSES: tuple[dict[str, Any], ...] = (
    {
        "prefix": "3.4",
        "severity": BLOCKING,
        "class_name": "Peptidase",
        "host_substrate": "Collagen, elastin, fibronectin, fibrinogen",
        "consequence": "Digests host structural protein. Not recoverable, and "
                       "in a fragment adjacent to a nerve the epineurium that "
                       "holds the nerve in place is itself collagen.",
    },
    {
        "prefix": "3.1.1.3",
        "severity": SERIOUS,
        "class_name": "Triacylglycerol lipase",
        "host_substrate": "Host triglyceride, adipose tissue",
        "consequence": "Hydrolyses host fat at the injection site. Local and "
                       "bounded, but it has to be bounded experimentally "
                       "rather than assumed.",
    },
    {
        "prefix": "1.11.1",
        "severity": SERIOUS,
        "class_name": "Peroxidase",
        "host_substrate": "Lipids, proteins and DNA, via oxidative damage",
        "consequence": "Oxidative stress in a site that is already inflamed, "
                       "where activated neutrophils are generating peroxide "
                       "as part of the respiratory burst.",
    },
    {
        "prefix": "3.1.1",
        "severity": CAUTION,
        "class_name": "Carboxylic-ester hydrolase",
        "host_substrate": "Host esters, promiscuously",
        "consequence": "Esterase activity is frequently promiscuous. Bound it "
                       "experimentally rather than on classification.",
    },
    {
        "prefix": "3.2.1",
        "severity": CAUTION,
        "class_name": "Glycosidase",
        "host_substrate": "Glycosaminoglycans, glycoproteins",
        "consequence": "Acts on host sugars, including the matrix the carrier "
                       "itself is made of where that carrier is hyaluronic "
                       "acid.",
    },
)

# For entries with no EC number at all. A missing classification must not mean
# a missing flag: the warehouse holds two entries named only "protease" and
# "serineprotease", and an EC-only filter would pass both.
NAME_MARKERS: tuple[dict[str, Any], ...] = (
    {
        "markers": ("protease", "proteinase", "peptidase", "collagenase",
                    "elastase", "trypsin", "chymotrypsin", "subtilisin",
                    "thermolysin", "papain", "bromelain"),
        "severity": BLOCKING,
        "class_name": "Peptidase (by name; no EC recorded)",
        "host_substrate": "Host proteins (peptide bonds)",
        "consequence": "Named as a protease with no EC number to screen on. "
                       "Treated as its name says, because an unclassified "
                       "protease is not a safe one.",
    },
    {
        "markers": ("lipase",),
        "severity": SERIOUS,
        "class_name": "Lipase (by name; no EC recorded)",
        "host_substrate": "Host triglyceride",
        "consequence": "Named as a lipase with no EC number to screen on.",
    },
    {
        "markers": ("hyaluronidase",),
        "severity": SERIOUS,
        "class_name": "Hyaluronidase (by name; no EC recorded)",
        "host_substrate": "Hyaluronic acid, in tissue and in the carrier",
        "consequence": "Degrades the carrier's own backbone where that "
                       "backbone is hyaluronic acid, as well as host matrix.",
    },
)


def _ec_match(ec_numbers: Iterable[str]) -> dict[str, Any] | None:
    """Longest matching prefix, so 3.1.1.3 is a lipase and not just an ester."""
    best: dict[str, Any] | None = None
    for ec in ec_numbers or ():
        for cls in EC_CLASSES:
            if ec.startswith(cls["prefix"]):
                if best is None or len(cls["prefix"]) > len(best["prefix"]):
                    best = cls
                elif (len(cls["prefix"]) == len(best["prefix"])
                      and _RANK[cls["severity"]] < _RANK[best["severity"]]):
                    best = cls
    return best


def _name_match(name: str) -> dict[str, Any] | None:
    low = (name or "").lower()
    for rule in NAME_MARKERS:
        if any(m in low for m in rule["markers"]):
            return rule
    return None


def screen_reagent(name: str, ec_numbers: Iterable[str] = ()) -> dict[str, Any]:
    """Screen anything proposed for injection, in the warehouse or not.

    Takes a name and EC numbers rather than a Protein, so that a reagent the
    warehouse has never heard of goes through the same gate. That is not a
    convenience: the carrier document proposes collagenase to clear the protein
    corona, collagenase is EC 3.4.24.3, and the screen has to reach it.
    """
    ec_numbers = list(ec_numbers or ())
    hit = _ec_match(ec_numbers)
    basis = f"EC {hit['prefix']}" if hit else None
    if hit is None and not ec_numbers:
        hit = _name_match(name)
        basis = "name" if hit else None

    if hit is None:
        return {
            "severity": UNFLAGGED,
            "is_screened": False,
            "basis": None,
            "class_name": None,
            "host_substrate": None,
            "consequence": None,
            "statement": (
                "No host-substrate activity flagged from its classification. "
                "That is not evidence of selectivity: it has not been tested "
                "against human tissue, and not asking is not the same as a "
                "negative answer."
            ),
        }
    return {
        "severity": hit["severity"],
        "is_screened": True,
        "basis": basis,
        "class_name": hit["class_name"],
        "host_substrate": hit["host_substrate"],
        "consequence": hit["consequence"],
        "statement": (
            f"{hit['class_name']} by {basis}. Acts on "
            f"{hit['host_substrate'].lower()}. {hit['consequence']}"
        ),
    }


def screen(protein: Any) -> dict[str, Any]:
    """Screen a warehouse protein."""
    return screen_reagent(getattr(protein, "name", "") or "",
                          getattr(protein, "ec_numbers", None) or ())


def sort_key(protein: Any) -> int:
    """Ascending sort order: unflagged first, blocking last.

    SEVERITY_ORDER runs worst-first because that is how a reader wants the
    severities listed, so this inverts it. Sorting on _RANK directly put every
    refused protease at the top of the PLA pool, which is the exact opposite of
    the gate.
    """
    return len(SEVERITY_ORDER) - 1 - _RANK[screen(protein)["severity"]]


def is_blocking(protein: Any) -> bool:
    return screen(protein)["severity"] == BLOCKING


def summary(proteins: Iterable[Any]) -> dict[str, Any]:
    """Counts per severity, for a page that wants to quote the screen.

    Exported rather than recomputed in a page, because the safety review page
    quoted 5/6/33/461 from a computation that had drifted from the warehouse
    by the time anyone checked.
    """
    proteins = list(proteins)
    counts = {s: 0 for s in SEVERITY_ORDER}
    examples: dict[str, list[str]] = {s: [] for s in SEVERITY_ORDER}
    for p in proteins:
        sev = screen(p)["severity"]
        counts[sev] += 1
        if sev != UNFLAGGED and len(examples[sev]) < 8:
            examples[sev].append(getattr(p, "name", "?"))
    return {
        "total": len(proteins),
        "counts": counts,
        "examples": examples,
        "screened": sum(counts[s] for s in SEVERITY_ORDER if s != UNFLAGGED),
        "note": (
            "Severity comes from enzyme classification, which is not proof of "
            "harm in situ -- an enzyme tethered inside a hydrogel is not the "
            "same exposure as free enzyme in tissue. The burden of proof is "
            "placed deliberately: a protease proposed for injection next to a "
            "nerve should have to show it does not digest tissue, rather than "
            "be assumed safe because nobody checked."
        ),
    }


# Reagents proposed outside the warehouse, screened so the proposal and the
# screen cannot drift apart. Stage 0 of the carrier document proposes the first
# of these by name.
PROPOSED_REAGENTS: tuple[dict[str, Any], ...] = (
    {
        "name": "Collagenase clostridium histolyticum (XIAFLEX)",
        "ec_numbers": ["3.4.24.3"],
        "proposed_for": "Stage 0 -- clearing the protein corona and the "
                        "fibrotic capsule so the catalyst can reach the "
                        "surface.",
        "label_says": (
            "Section 5.1 of the FDA label warns against injection into "
            "tendons, nerves, blood vessels or other collagen-containing "
            "structures, and reports flexor tendon rupture, pulley rupture, "
            "ligament injury, CRPS and sensory abnormality in trials."
        ),
        "the_conflict": (
            "This product is defined as treating fragments in high-risk "
            "anatomical locations, which means adjacent to nerves and vessels. "
            "That is the anatomy the label excludes, so the reagent is cited "
            "in support of a step its own label warns against."
        ),
    },
)
