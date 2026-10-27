"""Layer 2b -- rank the candidates.

This ranks *strength of evidence plus fit to body conditions*. It is not an
activity predictor: nothing in the public record ties a sequence to a turnover
rate on a solid fragment inside muscle, so claiming a predicted rate would be
inventing one. Every signal below is either measured and cited, or reported as
unknown and counted against the confidence.
"""
from __future__ import annotations

from .schema import (
    BODY_PH,
    BODY_TEMPERATURE_C,
    Gap,
    Protein,
    ScoredCandidate,
)

# Explicit so the ranking can be audited and argued with.
WEIGHTS: dict[str, float] = {
    "replication": 0.30,   # independent papers reporting activity on this material
    "temperature_fit": 0.25,
    "ph_fit": 0.20,
    "curation": 0.15,      # Swiss-Prot reviewed
    "structure": 0.10,     # an experimental structure exists
}

# Beyond these distances from body conditions the optimum tells us the enzyme
# is working off-design, which becomes an engineering target rather than a
# disqualification.
TEMP_TOLERANCE_C = 15.0
PH_TOLERANCE = 2.0

# What an unmeasured signal is worth. Scoring only over the signals that happen
# to be present would hand a perfect score to the enzyme nobody characterised,
# so an absent measurement counts as neutral evidence at its full weight and
# can never lift a candidate above one that was actually measured.
NEUTRAL_PRIOR = 0.5


class Summary:
    """Several papers often report the same optimum differently.

    Taking whichever value happens to be first would make the ranking depend on
    ingest order, and taking the one nearest body conditions would be
    cherry-picking. The median is used instead, and the spread is carried
    alongside so a disagreement between labs stays visible.
    """

    __slots__ = ("value", "observation", "spread", "n")

    def __init__(self, value: float, observation, spread: float, n: int):
        self.value = value
        self.observation = observation
        self.spread = spread
        self.n = n

    @property
    def evidence(self):
        return self.observation.evidence

    def confidence(self, tolerance: float) -> float:
        """How much the median is worth believing, given how the values scatter.

        A median is only a summary. Four measurements of 25, 25, 50 and 55 have
        a median of 37.5, which lands on body temperature although not one lab
        measured anything near it. Treating that as a perfect match would let
        an artefact of the arithmetic outrank an enzyme whose measurements
        genuinely cluster where we need them, so confidence falls as the values
        disagree.
        """
        if self.n <= 1:
            return 1.0
        return 1.0 / (1.0 + self.spread / tolerance)

    def describe(self, unit: str) -> str:
        if self.n == 1:
            return f"{self.value:g} {unit}".strip()
        return (
            f"median {self.value:g} {unit} over {self.n} measurements "
            f"(range {self.spread:g})".strip()
        )


def _summarise(protein: Protein, metric: str) -> Summary | None:
    """Median of every measured value for a metric, with its spread."""
    measured = [o for o in protein.observations_for(metric) if o.value is not None]
    if not measured:
        return None
    values = sorted(o.value for o in measured)
    mid = len(values) // 2
    median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
    # Cite the measurement closest to the median, so the number shown and the
    # paper cited for it agree.
    closest = min(measured, key=lambda o: abs(o.value - median))
    return Summary(median, closest, values[-1] - values[0], len(measured))


def _fit(delta: float, tolerance: float) -> float:
    return max(0.0, 1.0 - delta / tolerance)


def _scattered_fit(summary: "Summary", target: float, tolerance: float) -> float:
    """Fit to a body condition, discounted by how far the measurements scatter.

    Scattered values are pulled back toward the neutral prior: the median still
    points the right way, it just carries less weight than a tight cluster.
    """
    raw = _fit(abs(summary.value - target), tolerance)
    confidence = summary.confidence(tolerance)
    return raw * confidence + NEUTRAL_PRIOR * (1.0 - confidence)


def score(protein: Protein) -> ScoredCandidate:
    reasons: list[str] = []
    unknowns: list[str] = []
    gaps: list[Gap] = []
    parts: dict[str, float] = {}

    # --- replication -------------------------------------------------------
    papers = protein.publication_count()
    if papers:
        parts["replication"] = min(1.0, papers / 3.0)
        reasons.append(
            f"activity reported in {papers} independent publication"
            f"{'s' if papers != 1 else ''}"
        )
    else:
        unknowns.append("replication")

    # --- temperature -------------------------------------------------------
    temp = _summarise(protein, "temperature_optimum_c")
    if temp is not None:
        delta = abs(temp.value - BODY_TEMPERATURE_C)
        parts["temperature_fit"] = _scattered_fit(
            temp, BODY_TEMPERATURE_C, TEMP_TOLERANCE_C
        )
        reasons.append(
            f"temperature optimum {temp.describe('C')} vs body "
            f"{BODY_TEMPERATURE_C:g} C ({temp.evidence.citation()})"
        )
        if temp.n > 1 and temp.confidence(TEMP_TOLERANCE_C) < 0.6:
            reasons.append(
                f"temperature measurements disagree across {temp.spread:g} C, "
                "so the median is discounted"
            )
            # Not knowing the optimum is itself work the lab has to do, and it
            # would otherwise go unreported whenever the median lands on target.
            gaps.append(
                Gap(
                    kind="temperature spread",
                    detail=(
                        f"{temp.n} publications disagree across {temp.spread:g} C "
                        f"({', '.join(f'{o.value:g}' for o in sorted(protein.observations_for('temperature_optimum_c'), key=lambda o: o.value or 0) if o.value is not None)} C), "
                        "so this enzyme's optimum is not actually established"
                    ),
                    measured=temp.describe("C"),
                    target="one assay at 37 C under comparable conditions",
                    engineering_target="re-measure activity at body temperature before relying on the median",
                    evidence=temp.evidence,
                )
            )
        if delta > 5.0:
            gaps.append(
                Gap(
                    kind="temperature",
                    detail=(
                        f"optimum {temp.value:g} C is {delta:.0f} C from body temperature"
                    ),
                    measured=temp.describe("C"),
                    target=f"{BODY_TEMPERATURE_C:g} C",
                    engineering_target="shift the activity optimum toward 37 C and hold the fold stable there",
                    evidence=temp.evidence,
                )
            )
    else:
        unknowns.append("temperature_optimum")
        gaps.append(
            Gap(
                kind="temperature",
                detail="no temperature optimum curated for this enzyme",
                measured=None,
                target=f"{BODY_TEMPERATURE_C:g} C",
                engineering_target="measure activity at 37 C before any design work",
            )
        )

    # --- pH ----------------------------------------------------------------
    ph = _summarise(protein, "ph_optimum")
    if ph is not None:
        delta = abs(ph.value - BODY_PH)
        parts["ph_fit"] = _scattered_fit(ph, BODY_PH, PH_TOLERANCE)
        reasons.append(
            f"pH optimum {ph.describe('')} vs body {BODY_PH:g} "
            f"({ph.evidence.citation()})"
        )
        if ph.n > 1 and ph.confidence(PH_TOLERANCE) < 0.6:
            reasons.append(
                f"pH measurements disagree across {ph.spread:g} units, "
                "so the median is discounted"
            )
        if delta > 0.5:
            gaps.append(
                Gap(
                    kind="ph",
                    detail=f"optimum pH {ph.value:g} is {delta:.1f} units from body pH",
                    measured=f"pH {ph.describe('')}",
                    target=f"pH {BODY_PH:g}",
                    engineering_target="re-tune the active-site electrostatics for neutral pH",
                    evidence=ph.evidence,
                )
            )
    else:
        unknowns.append("ph_optimum")
        gaps.append(
            Gap(
                kind="ph",
                detail="no pH optimum curated for this enzyme",
                measured=None,
                target=f"pH {BODY_PH:g}",
                engineering_target="measure activity at pH 7.4 before any design work",
            )
        )

    # --- curation and structure -------------------------------------------
    if protein.reviewed:
        parts["curation"] = 1.0
        reasons.append("Swiss-Prot reviewed entry")
    elif protein.reviewed is None:
        unknowns.append("uniprot_review_status")
    else:
        parts["curation"] = 0.0

    if protein.pdb_ids:
        parts["structure"] = 1.0
        reasons.append(f"experimental structure available ({protein.pdb_ids[0]})")
    else:
        parts["structure"] = 0.0
        gaps.append(
            Gap(
                kind="structure",
                detail="no experimental structure; design would start from a prediction",
                measured=None,
                target="experimental structure or high-confidence model",
                engineering_target="obtain a structure before active-site redesign",
            )
        )

    # Every weight is spent: a signal we measured contributes its value, one we
    # did not contributes the neutral prior. Confidence is reported separately
    # as the share of weight that rests on the prior rather than on a number.
    measured_weight = sum(WEIGHTS[k] for k in parts if k in WEIGHTS)
    value = sum(
        WEIGHTS[k] * parts.get(k, NEUTRAL_PRIOR) for k in WEIGHTS
    ) / sum(WEIGHTS.values())
    uncertainty = 1.0 - (measured_weight / sum(WEIGHTS.values()))

    return ScoredCandidate(
        protein=protein,
        score=round(value, 4),
        uncertainty=round(uncertainty, 4),
        reasons=reasons,
        unknowns=unknowns,
        gaps=gaps,
    )


def rank(proteins: list[Protein]) -> list[ScoredCandidate]:
    scored = [score(p) for p in proteins]
    # Confident evidence first; ties broken toward the better-documented entry.
    scored.sort(
        key=lambda c: (
            -c.score,
            c.uncertainty,
            -c.protein.publication_count(),
            c.protein.name,
        )
    )
    return scored
