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

from . import formulate, goals, metals, pipeline, substrate
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


def _kinetics(p: Protein) -> dict[str, Any]:
    """What the catalytic constants were measured on, by class."""
    obs = [o for o in p.observations
           if o.metric in substrate.KINETIC_METRICS and o.value is not None]
    if not obs:
        return {"n": 0, "classes": {}, "strongest": None}
    classes = [substrate.classify((o.conditions or {}).get("substrate")) for o in obs]
    return {
        "n": len(obs),
        "classes": {k: classes.count(k) for k in substrate.ORDER if classes.count(k)},
        "labels": substrate.LABEL,
        "strongest": substrate.best(classes),
    }


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
        "kinetics": _kinetics(p),
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



# Full names, so the interface can say "Polyethylene terephthalate" rather than
# leaving a clinician to decode PBAT. PAZy carries a name beside every
# abbreviation it records, and those are read out of the warehouse below.
#
# The rest need a table, for two different reasons. PE, PP, PS and PVC have no
# substrate record at all, because no enzyme in the seed set acts on them --
# their absence is the finding. The metals and minerals were never in PAZy to
# begin with; they are here because a clinician will ask about them, and "no
# enzymatic route exists" is a useful answer.
_EXTRA_NAMES = {
    "PE": "Polyethylene",
    "PP": "Polypropylene",
    "PS": "Polystyrene",
    "PVC": "Polyvinyl chloride",
    "steel": "Steel",
    "iron": "Iron",
    "lead": "Lead",
    "aluminium": "Aluminium",
    "titanium": "Titanium",
    "glass": "Glass",
    "silica": "Silica",
    "ceramic": "Ceramic",
    "stone": "Stone",
}


def material_names(proteins: list[Protein]) -> dict[str, str]:
    """Abbreviation to full name, preferring what the source database says."""
    names: dict[str, str] = {}
    for protein in proteins:
        for sub in protein.substrates or []:
            if not isinstance(sub, dict):
                continue
            abbr = (sub.get("abbreviation") or "").strip()
            name = (sub.get("name") or "").strip()
            if abbr and name:
                names.setdefault(abbr, name)
    for abbr, name in _EXTRA_NAMES.items():
        names.setdefault(abbr, name)
    return names


def build(proteins: list[Protein], max_alternatives: int = 5) -> dict[str, Any]:
    decisions: dict[str, Any] = {}
    for key in materials(proteins):
        spec = MaterialSpec(polymer=key, mass_mg=REFERENCE_MASS_MG)
        decision = decide(spec, proteins, max_alternatives=max_alternatives)
        burden = _burden(key) if decision.verdict == "enzyme_selected" else None
        decisions[key] = {
            "material": key,
            "verdict": decision.verdict,
            "rationale": decision.rationale,
            "selected": _candidate(decision.selected) if decision.selected else None,
            "alternatives": [_candidate(c) for c in decision.alternatives],
            "burden": burden,
            # Downstream stages are a design specification, not a computation.
            # They ship with an evidence class per item so the interface can
            # keep them visually distinct from the measured selection above.
            "downstream": pipeline.build(
                key, (burden or {}).get("products", [])
            ) if decision.verdict == "enzyme_selected" else None,
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
        # Crystallinity and particle size are free inputs, so the page applies
        # these rules itself. Exporting the thresholds and the wording keeps
        # one source of truth instead of a second copy written in JavaScript.
        # The goal modes are computed in the browser, because changing the
        # goal must change the answer without a round trip. Exporting the
        # thresholds and the wording keeps one source of truth: the page
        # cannot drift from f2c/goals.py by paraphrasing it.
        # The structure page used to live separately; the unified page needs
        # to say what the viewer is actually showing, which is a near-identical
        # crystal structure rather than the selected protein itself.
        "structure": {
            "pdb_id": "4CG1",
            "note": "4CG1 is an experimental crystal structure, not a prediction. "
                    "It is 259 of 261 residues identical to Q6A0I4, the selected "
                    "enzyme, differing at S18R and T136S -- so it is that close, "
                    "not that enzyme. AlphaFold does model Q6A0I4, but its file "
                    "server refused the download from this network and nothing "
                    "was substituted for it.",
        },
        "kinetics_total": sum(
            1 for p in proteins for o in p.observations
            if o.metric in substrate.KINETIC_METRICS and o.value is not None
        ),
        "material_names": material_names(proteins),
        # The metal arm. A second view rather than a replacement: the polymer
        # arm answers a different question and both are real cases, so the
        # page carries both and the reader picks.
        "metals": {
            "order": list(metals.METALS),
            "names": {k: v["name"] for k, v in metals.METALS.items()},
            "routes": {k: metals.route(k) for k in metals.METALS},
            "engineering": {k: metals.engineering_targets(k) for k in metals.METALS},
            "refs": metals.REFS,
            "carrier": metals.CARRIER_REQUIREMENTS,
            "corrosion_rates": metals.CORROSION_RATES_MM_PER_YEAR,
            # Constants rather than a precomputed answer, because the mass is
            # an input the reader changes.
            "capacity_constants": {
                "fe_g_per_mol": metals.FE_G_PER_MOL,
                "fe_atoms_per_shell": metals.FE_ATOMS_PER_SHELL,
                "shell_kda": metals.FERRITIN_SHELL_KDA,
                "metal_fraction": metals.METAL_FRACTION,
                "avogadro": metals.AVOGADRO,
            },
        },
        "goal_rules": {
            "max_useful_crystallinity_pct": goals.MAX_USEFUL_CRYSTALLINITY_PCT,
            "micro_size_mm": goals.MICRO_SIZE_MM,
            "labels": dict(goals.LABEL),
            "default_debulk_pct": 20.0,
        },
        "accessibility_rules": {
            "crystallinity_barrier_pct": formulate.CRYSTALLINITY_BARRIER_PCT,
            "crystallinity_high_pct": 45.0,
            "density_g_cm3": formulate.DENSITY_G_CM3,
            "text": {
                "unknown": "Crystallinity not characterised. It decides whether the "
                           "enzyme can reach the chain at all.",
                "barrier": "Enzymes act on amorphous regions. The crystalline fraction "
                           "resists attack and sets the ceiling on how much of this "
                           "fragment can be degraded at all.",
                "surrogate": "The selected enzyme's constants come from soluble "
                             "substrates, where crystallinity does not apply, so they "
                             "say nothing about this barrier.",
                "corona": "A fragment in tissue carries adsorbed plasma protein and, "
                          "in trauma, soil and blood. The enzyme meets that layer, "
                          "not the polymer.",
                "area_basis": "Cubes of the stated edge length filling the fragment "
                              "volume. Surface erosion scales with this, not with mass; "
                              "no rate is derived from it.",
            },
        },
        "decisions": decisions,
    }


def write(payload: dict[str, Any], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return dest
