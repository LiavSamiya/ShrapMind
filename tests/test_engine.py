"""Tests for the quality rules the product promises to enforce."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest

from f2c import rank, warehouse
from f2c.engine import decide
from f2c.formulate import capture_requirement
from f2c.rank import score
from f2c.retrieve import retrieve
from f2c.schema import Evidence, MaterialSpec, Observation, Protein
from f2c.sources import brenda

STORE = Path(__file__).resolve().parent.parent / "data" / "warehouse.json"
TODAY = _dt.date.today().isoformat()


@pytest.fixture(scope="module")
def proteins() -> list[Protein]:
    if not STORE.exists():
        pytest.skip("warehouse not built; run `python -m f2c.cli build`")
    return warehouse.load(STORE)


def _protein(**kw) -> Protein:
    base = dict(
        protein_id="test:1",
        name="Test enzyme",
        sequence="MA",
        sequence_md5="x",
        organism="Testus",
        taxon_id=None,
        substrates=[{"abbreviation": "PET", "oligomer_only": False}],
        uniprot_accession="P00000",
        evidence=[Evidence(source_db="test", retrieved_at=TODAY, level="experimental")],
        literature=[{"doi": "10.1/a"}, {"doi": "10.1/b"}, {"doi": "10.1/c"}],
    )
    base.update(kw)
    return Protein(**base)


def _obs(metric: str, value: float) -> Observation:
    return Observation(
        metric=metric,
        value=value,
        unit="C" if metric.endswith("_c") else "pH",
        evidence=Evidence(
            source_db="UniProtKB", retrieved_at=TODAY, level="experimental", pmid="1"
        ),
    )


# --- provenance ---------------------------------------------------------

def test_every_observation_carries_evidence(proteins):
    """No number may travel without the source that reported it."""
    for p in proteins:
        for obs in p.observations:
            assert obs.evidence.source_db
            assert obs.evidence.retrieved_at
            assert obs.evidence.level in {
                "experimental", "curated", "predicted", "assumed"
            }


def test_every_protein_has_evidence(proteins):
    assert proteins
    for p in proteins:
        assert p.evidence, f"{p.protein_id} has no evidence trail"


def test_measurements_are_not_averaged(proteins):
    """Km values stay as separate rows, each with its own substrate context."""
    multi = [p for p in proteins if len(p.observations_for("km")) > 1]
    for p in multi:
        contexts = [o.conditions.get("substrate") for o in p.observations_for("km")]
        assert len(contexts) == len(p.observations_for("km"))


# --- the two kinds of "no" ---------------------------------------------

@pytest.mark.parametrize("material", ["glass", "steel", "lead", "ceramic"])
def test_non_enzymatic_materials_are_blocked_with_a_reason(proteins, material):
    decision = decide(MaterialSpec(polymer=material, mass_mg=50), proteins)
    assert decision.verdict == "no_pathway"
    assert decision.selected is None
    assert len(decision.rationale) > 40, "a refusal must carry its reason"


def test_absent_evidence_is_not_reported_as_impossible(proteins):
    """PE has no verified enzyme, which is not the same as having no pathway."""
    decision = decide(MaterialSpec(polymer="PE", mass_mg=40), proteins)
    assert decision.verdict == "no_pathway"
    assert "available evidence" in decision.rationale
    assert "indegradable" in decision.rationale


def test_oligomer_only_entries_excluded_for_solid_fragments():
    protein = _protein(
        substrates=[{"abbreviation": "PET", "oligomer_only": True}]
    )
    solid = retrieve(MaterialSpec(polymer="PET", form="polymer"), [protein])
    assert solid.candidates == []
    assert solid.oligomer_only_excluded == 1

    oligomer = retrieve(MaterialSpec(polymer="PET", form="oligomer"), [protein])
    assert len(oligomer.candidates) == 1


# --- ranking honesty ----------------------------------------------------

def test_unmeasured_enzyme_cannot_outrank_a_measured_good_fit():
    """Regression: scoring only over present signals gave ignorance a perfect score."""
    unmeasured = _protein(reviewed=True, pdb_ids=["1ABC"])
    measured = _protein(
        reviewed=True,
        pdb_ids=["1ABC"],
        observations=[_obs("temperature_optimum_c", 37.0), _obs("ph_optimum", 7.4)],
    )
    assert score(measured).score > score(unmeasured).score
    assert score(measured).uncertainty == 0.0
    assert score(unmeasured).uncertainty > 0.0


def test_poor_measured_fit_ranks_below_unknown():
    """A measured bad fit is worse news than no measurement, and must score lower."""
    unmeasured = _protein(reviewed=True, pdb_ids=["1ABC"])
    bad_fit = _protein(
        reviewed=True,
        pdb_ids=["1ABC"],
        observations=[_obs("temperature_optimum_c", 80.0), _obs("ph_optimum", 11.0)],
    )
    assert score(bad_fit).score < score(unmeasured).score


def test_disagreeing_measurements_use_the_median_not_the_first():
    """Ingest order must not decide the answer when labs disagree."""
    protein = _protein(
        observations=[
            _obs("temperature_optimum_c", 70.0),
            _obs("temperature_optimum_c", 37.0),
            _obs("temperature_optimum_c", 40.0),
        ]
    )
    summary = rank._summarise(protein, "temperature_optimum_c")
    assert summary.value == 40.0  # median, not the 70 that happens to be first
    assert summary.n == 3
    assert summary.spread == 33.0
    assert "median" in summary.describe("C")


def test_cited_paper_matches_the_number_shown():
    """The citation shown must belong to the value shown, not to another one."""
    protein = _protein(
        observations=[
            _obs("ph_optimum", 5.0),
            _obs("ph_optimum", 7.5),
            _obs("ph_optimum", 11.0),
        ]
    )
    summary = rank._summarise(protein, "ph_optimum")
    assert summary.value == 7.5
    assert summary.observation.value == 7.5


def test_brenda_suspect_references_are_detected():
    """A PMID too small for its publication year cannot be that paper."""
    entry = {
        "reference": {
            "1": {"pmid": 2937183, "year": 2018, "title": "A 2018 paper"},
            "2": {"pmid": 254050803, "year": 2014, "title": "Nine-digit pmid"},
            "3": {"pmid": 24728714, "year": 2014, "title": "A plausible one"},
            "4": {"pmid": 9910, "year": 1976, "title": "Genuinely old, genuinely short"},
        }
    }
    flagged = {s["reference_id"] for s in brenda.suspect_references(entry)}
    assert flagged == {"1", "2"}


def test_gaps_name_an_engineering_action():
    candidate = score(
        _protein(observations=[_obs("temperature_optimum_c", 70.0), _obs("ph_optimum", 9.0)])
    )
    assert candidate.gaps
    for gap in candidate.gaps:
        assert gap.engineering_target
        assert gap.target


# --- mass balance -------------------------------------------------------

def test_capture_capacity_scales_with_mass():
    small = capture_requirement("PET", 10.0)
    large = capture_requirement("PET", 100.0)
    assert small["computable"] and large["computable"]
    assert large["total_product_mmol"] == pytest.approx(
        small["total_product_mmol"] * 10, rel=1e-6
    )


def test_capture_declines_when_repeat_unit_is_undefined():
    result = capture_requirement("PUR", 50.0)
    assert result["computable"] is False
    assert "repeat-unit" in result["reason"]


def test_no_release_rate_is_claimed():
    result = capture_requirement("PET", 50.0)
    assert "not reported" in result["rate"]


# --- end to end ---------------------------------------------------------

def test_pet_selection_is_fully_cited(proteins):
    decision = decide(MaterialSpec(polymer="PET", mass_mg=50, crystallinity_pct=35), proteins)
    assert decision.verdict == "enzyme_selected"
    chosen = decision.selected
    assert chosen.protein.literature, "selection must carry its evidence trail"
    assert chosen.protein.uniprot_accession
    assert decision.capture["computable"] is True
