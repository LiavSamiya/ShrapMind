"""What a catalytic constant was actually measured on.

A kcat is only evidence for the reaction it was measured on. Enzyme kinetics
are routinely run against soluble chromogenic esters because they are easy to
read in a plate reader, and those numbers then travel into databases beside
the enzyme's name with no note that the substrate was a proxy.

For this product the distinction decides whether a number means anything. The
question is turnover on a solid fragment in tissue; a constant measured on
4-nitrophenyl acetate does not answer it, however real the measurement is.

As built, of 289 kinetic measurements in the warehouse: 168 on chromogenic
model esters, 42 on soluble oligomers, 58 unrecorded, and none on a polymer.
"""
from __future__ import annotations

import re

POLYMER, OLIGOMER, MODEL, UNKNOWN = "polymer", "oligomer", "model", "unknown"

ORDER = [POLYMER, OLIGOMER, MODEL, UNKNOWN]

LABEL = {
    POLYMER: "the solid polymer",
    OLIGOMER: "a soluble oligomer of the target",
    MODEL: "a chromogenic model substrate",
    UNKNOWN: "an unrecorded substrate",
}

# Chromogenic and fluorogenic reporters: nitrophenyl esters for hydrolases,
# nitroanilide peptides for proteases. Convenient to assay, unrelated to a
# polymer surface.
_MODEL = re.compile(
    r"nitrophen|nitroanilide|\bpNP\b|p-?nitro|\bpNA\b|umbellifer|resorufin"
    r"|olive oil|tributyrin|triolein",
    re.I,
)
# Soluble break-down intermediates of the target polymer: BHET and MHET for
# PET, aminohexanoate oligomers for polyamide, 3HB oligomers for PHA. Closer
# to the real reaction than a reporter, still not the solid.
_OLIGOMER = re.compile(
    r"hydroxyethyl.?\)?terephthal|terephthalic acid|\bBHET\b|\bMHET\b"
    r"|oligomer|dimer|trimer|tetramer|pentamer|aminohexanoate",
    re.I,
)
# The solid itself, or a film or powder of it.
_POLYMER = re.compile(
    r"\bPET\b|\bPBAT\b|\bPLA\b|\bPHB\b|\bPCL\b|polyester|poly\(|polyethylene"
    r"|film|powder|nanoparticle|fibre|fiber|amorphous|crystalline",
    re.I,
)
# BRENDA's own placeholder for "see the comment".
_PLACEHOLDER = {"more", "?", "-", ""}


def classify(substrate: str | None) -> str:
    """Which kind of substrate a measurement was made against."""
    if substrate is None or substrate.strip().lower() in _PLACEHOLDER:
        return UNKNOWN
    text = substrate.strip()
    # Order matters: "bis(2-hydroxyethyl)terephthalate" contains neither a
    # reporter nor "poly", but an oligomer check must beat the polymer regex
    # for strings like "PET oligomer".
    if _MODEL.search(text):
        return MODEL
    if _OLIGOMER.search(text):
        return OLIGOMER
    if _POLYMER.search(text):
        return POLYMER
    return UNKNOWN


def best(classes: list[str]) -> str:
    """The strongest class present, by how much it tells us about the real reaction."""
    for kind in ORDER:
        if kind in classes:
            return kind
    return UNKNOWN


# How much a constant measured on each class counts as evidence that the
# enzyme turns over a solid fragment.
#
# These sit around the ranker's neutral prior of 0.5 rather than running down
# to zero, because a weak measurement must never score below no measurement at
# all. A reporter ester does prove the protein expresses, folds and is a live
# hydrolase, so it earns slightly more than silence -- and no more, because it
# says nothing about eroding a solid. The spread here is deliberately narrow:
# when nobody has measured the thing that matters, the honest signal is weak,
# and the gap text does the work the score cannot.
WEIGHT = {POLYMER: 1.0, OLIGOMER: 0.7, MODEL: 0.55, UNKNOWN: 0.5}

KINETIC_METRICS = ("kcat", "km", "kcat_km", "specific_activity")
