"""Export the engine's answers for the browser interface.

The page cannot run Python, so every decision is computed here and shipped as
data. The page displays it and does one piece of arithmetic: scaling the
product burden by fragment mass. That is exactly linear, so instead of
restating the repeat-unit masses in JavaScript — a second copy that could
drift from `formulate.REPEAT_UNIT_G_PER_MOL` — this exports `mmol_per_mg` and
the page multiplies.

Amino-acid sequences are dropped: nothing in the interface shows them, and
they are most of the payload.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from .engine import decide
from .formulate import REPEAT_UNIT_G_PER_MOL, capture_requirement
from .rank import BODY_PH, BODY_TEMPERATURE_C, WEIGHTS, _summarise
from .retrieve import ALIASES, NON_ENZYMATIC
from .schema import MaterialSpec, Protein, ScoredCandidate

# One reference mass for the burden; the page scales from it.
REFERENCE_MASS_MG = 1.0

# Metrics the interface draws on a scale against a body target.
SCALED_METRICS = {
    "temperature_optimum_c": {"label": "Temperature optimum", "unit": "°C", "target": BODY_TEMPERATURE_C},
    "ph_optimum": {"label": "pH optimum", "unit": "", "target": BODY_PH},
}


def _measurements(protein: Protein, metric: str) -> list[dict[str, Any]]:
    """Every individual measurement, so the page can show the spread.

    A median alone would let the interface imply a precision the literature
    does not have. The points are what make a disagreement between labs
    visible rather than merely stated.
    """
    out = []
    for obs in protein.observations_for(metric):
        if obs.value is None:
            continue
        out.append(
            {
                "value": obs.value,
                "unit": obs.unit,
                "pmid": obs.evidence.pmid,
                "source": obs.evidence.source_db,
                "conditions": {
                    k: v for k, v in obs.conditions.items() if k != "all_pmids"
                },
            }
        )
    return out


def _candidate(candidate: ScoredCandidate) -> dict[str, Any]:
    p = candidate.protein
    signals = {}
    for metric, meta in SCALED_METRICS.items():
        points = _measurements(p, metric)
        summary = _summarise(p, metric)
        signals[metric] = {
            "label": meta["label"],
            "unit": meta["unit"],
            "target": meta["target"],
            "measurements": points,
            "median": summary.value if summary else None,
            "spread": summary.spread if summary else None,
            "n": summary.n if summary else 0,
            "cited_pmid": summary.evidence.pmid if summary else None,
        }

    return {
        "id": p.protein_id,
        "name": p.name,
        "organism": p.organism,
        "uniprot": p.uniprot_accession,
        "reviewed": p.reviewed,
        "ec": p.ec_numbers,
        "rhea": p.rhea_ids,
        "reactions": p.catalytic_reactions[:2],
        "pdb": p.pdb_ids[:8],
        "alphafold": p.alphafold_url,
        "score": candidate.score,
        "uncertainty": candidate.uncertainty,
        "publications": p.publication_count(),
        "reasons": candidate.reasons,
        "unknowns": candidate.unknowns,
        "signals": signals,
        "gaps": [
            {
                "kind": g.kind,
                "detail": g.detail,
                "measured": g.measured,
                "target": g.target,
                "action": g.engineering_target,
                "pmid": g.evidence.pmid if g.evidence else None,
            }
            for g in candidate.gaps
        ],
        "literature": [
            {
                "title": (lit.get("title") or "").strip(),
                "year": lit.get("year"),
                "doi": lit.get("doi"),
            }
            for lit in p.literature[:12]
        ],
    }


def _burden(material_key: str) -> dict[str, Any]:
    """Product burden per milligram, for the page to scale."""
    reference = capture_requirement(material_key, REFERENCE_MASS_MG)
    if not reference.get("computable"):
        return {"computable": False, "reason": reference.get("reason"), "products": reference.get("products", [])}
    return {
        "computable": True,
        "mmol_per_mg": reference["total_product_mmol"],
        "capture_mmol_per_mg": reference["capture_capacity_mmol"],
        "repeat_unit_g_per_mol": reference["repeat_unit_g_per_mol"],
        "products": reference["products"],
        "requires_capture": reference["requires_active_capture"],
        "metabolic": reference["metabolically_cleared"],
        "rate_note": reference["rate"],
    }


def materials(proteins: list[Protein]) -> list[str]:
    """Everything the interface offers, refusals included.

    The two kinds of "no" are a feature of the engine, so they have to be
    reachable from the interface rather than hidden behind an unsupported
    input.
    """
    degradable = sorted(
        {
            sub.get("abbreviation")
            for p in proteins
            for sub in p.substrates
            if sub.get("abbreviation")
        }
    )
    # Polymers PAZy names but has no verified enzyme for, plus the materials
    # with no enzymatic route at all.
    no_enzyme = sorted({v for v in ALIASES.values() if v not in degradable})
    return degradable + no_enzyme + sorted(NON_ENZYMATIC)


def build(proteins: list[Protein], max_alternatives: int = 5) -> dict[str, Any]:
    decisions: dict[str, Any] = {}
    for key in materials(proteins):
        spec = MaterialSpec(polymer=key, mass_mg=REFERENCE_MASS_MG)
        decision = decide(spec, proteins, max_alternatives=max_alternatives)
        decisions[key] = {
            "material": key,
            "verdict": decision.verdict,
            "rationale": decision.rationale,
            "selected": _candidate(decision.selected) if decision.selected else None,
            "alternatives": [_candidate(c) for c in decision.alternatives],
            "burden": _burden(key) if decision.verdict == "enzyme_selected" else None,
        }

    return {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "body": {"temperature_c": BODY_TEMPERATURE_C, "ph": BODY_PH},
        "weights": WEIGHTS,
        "warehouse": {
            "proteins": len(proteins),
            "with_uniprot": sum(1 for p in proteins if p.uniprot_accession),
            "reviewed": sum(1 for p in proteins if p.reviewed),
            "with_temperature": sum(
                1 for p in proteins if _summarise(p, "temperature_optimum_c")
            ),
            "with_ph": sum(1 for p in proteins if _summarise(p, "ph_optimum")),
        },
        "polymers_with_repeat_unit": sorted(REPEAT_UNIT_G_PER_MOL),
        "decisions": decisions,
    }


def write(payload: dict[str, Any], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return dest
