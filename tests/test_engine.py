"""Tests for the quality rules the product promises to enforce."""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pytest

from f2c import rank, warehouse
from f2c.engine import decide
from f2c.formulate import capture_requirement
from f2c.rank import score
from f2c.retrieve import retrieve
from f2c.schema import Evidence, MaterialSpec, Observation, Protein
from f2c.sources import brenda
from f2c import substrate

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
        observations=[
            _obs("temperature_optimum_c", 37.0),
            _obs("ph_optimum", 7.4),
            # Every scored signal has to be present for uncertainty to reach
            # zero, catalytic evidence included.
            Observation(
                metric="kcat", value=2.0, unit="1/s",
                evidence=Evidence(source_db="BRENDA", retrieved_at=TODAY,
                                  level="experimental", pmid="2"),
                conditions={"substrate": "PET film"},
            ),
        ],
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


def test_a_median_nobody_measured_does_not_score_as_a_perfect_match():
    """Regression: a bimodal spread produced an artefact median on target.

    TfH is measured at 25, 25, 50 and 55 C. The median is 37.5, which sits on
    body temperature although no lab measured anything near it. Scoring that
    as a near-perfect match ranked it above an enzyme whose measurements
    genuinely cluster near 37.
    """
    scattered = _protein(
        observations=[
            _obs("temperature_optimum_c", v) for v in (25.0, 25.0, 50.0, 55.0)
        ]
    )
    clustered = _protein(
        observations=[_obs("temperature_optimum_c", v) for v in (36.0, 37.0, 38.0)]
    )

    spread_summary = rank._summarise(scattered, "temperature_optimum_c")
    tight_summary = rank._summarise(clustered, "temperature_optimum_c")
    assert spread_summary.value == 37.5, "the artefact median is still produced"

    scattered_fit = rank._scattered_fit(spread_summary, 37.0, rank.TEMP_TOLERANCE_C)
    clustered_fit = rank._scattered_fit(tight_summary, 37.0, rank.TEMP_TOLERANCE_C)
    assert clustered_fit > scattered_fit, "agreement must beat coincidence"
    assert scattered_fit < 0.75, "a 30 C disagreement cannot read as a good match"


def test_confidence_falls_as_measurements_disagree():
    tight = _protein(observations=[_obs("ph_optimum", 7.4), _obs("ph_optimum", 7.5)])
    wide = _protein(observations=[_obs("ph_optimum", 5.0), _obs("ph_optimum", 11.0)])
    assert rank._summarise(tight, "ph_optimum").confidence(rank.PH_TOLERANCE) > 0.9
    assert rank._summarise(wide, "ph_optimum").confidence(rank.PH_TOLERANCE) < 0.3


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


def test_verified_bad_pmids_are_dropped_from_import():
    """The heuristic misses a real PMID on the wrong paper; the blocklist must not.

    PMID 18355276 is 8 digits and plausibly dated, so suspect_references lets
    it through. Resolving it showed it points at a different paper, and that
    finding has to survive into the import.
    """
    entry = {
        "protein": {"1": {"accessions": ["P00000"]}},
        "reference": {"5": {"pmid": 18355276, "year": 2008, "title": "Plausible"}},
        "temperature_optimum": [
            {"value": "55", "proteins": ["1"], "references": ["5"], "comment": ""}
        ],
    }
    assert brenda.suspect_references(entry) == [], "heuristic cannot catch this one"

    kept = list(brenda.observations_for_accession(entry, "P00000"))
    assert len(kept) == 1

    dropped = list(
        brenda.observations_for_accession(entry, "P00000", bad_pmids={"18355276"})
    )
    assert dropped == []


def test_substrate_classes_separate_proxies_from_the_real_thing():
    assert substrate.classify("4-nitrophenyl acetate") == substrate.MODEL
    assert substrate.classify("N-succinyl-Ala-Ala-Pro-Phe-4-nitroanilide") == substrate.MODEL
    assert substrate.classify("bis(2-hydroxyethyl)terephthalate") == substrate.OLIGOMER
    assert substrate.classify("amorphous PET film") == substrate.POLYMER
    assert substrate.classify("more") == substrate.UNKNOWN
    assert substrate.classify(None) == substrate.UNKNOWN


def test_weak_kinetics_never_score_below_no_kinetics():
    """A reporter-ester constant proves the protein is a live hydrolase.

    It says nothing about eroding a solid, so it must not lift the score much
    -- but scoring it below silence would punish having measured anything.
    """
    assert substrate.WEIGHT[substrate.MODEL] >= rank.NEUTRAL_PRIOR
    assert substrate.WEIGHT[substrate.POLYMER] > substrate.WEIGHT[substrate.OLIGOMER]
    assert substrate.WEIGHT[substrate.OLIGOMER] > substrate.WEIGHT[substrate.MODEL]


def test_no_warehouse_enzyme_claims_polymer_level_kinetics(proteins):
    """Every constant in the warehouse was measured on a surrogate.

    If this ever fails, someone has added real polymer kinetics and the gap
    text below it needs revisiting -- which would be good news.
    """
    classes = {
        substrate.classify((o.conditions or {}).get("substrate"))
        for p in proteins for o in p.observations
        if o.metric in substrate.KINETIC_METRICS and o.value is not None
    }
    assert substrate.POLYMER not in classes


def test_crystallinity_changes_the_answer(proteins):
    """Regression: it was accepted, printed, and ignored."""
    low = decide(MaterialSpec(polymer="PET", mass_mg=50, crystallinity_pct=5), proteins)
    high = decide(MaterialSpec(polymer="PET", mass_mg=50, crystallinity_pct=60), proteins)
    kinds = lambda d: {g["kind"]: g["severity"] for g in d.fragment["accessibility"]}
    assert "crystallinity" not in kinds(low)
    assert kinds(high)["crystallinity"] == "high"


def test_particle_size_changes_surface_area(proteins):
    coarse = decide(MaterialSpec(polymer="PET", mass_mg=50, particle_size_mm=4), proteins)
    fine = decide(MaterialSpec(polymer="PET", mass_mg=50, particle_size_mm=0.5), proteins)
    a = coarse.fragment["geometry"]["specific_area_mm2_per_mg"]
    b = fine.fragment["geometry"]["specific_area_mm2_per_mg"]
    assert b > a * 4, "smaller particles must expose far more surface"


def test_surface_area_is_not_turned_into_a_rate(proteins):
    d = decide(MaterialSpec(polymer="PET", mass_mg=50, particle_size_mm=1), proteins)
    blob = json.dumps(d.fragment).lower()
    for forbidden in ("per hour", "per day", "mg/h", "half-life", "days to"):
        assert forbidden not in blob


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


# --- the structure page's numbering guard ----------------------------------
# UniProt numbers the precursor, the PDB entry numbers the mature protein, and
# the two differ by the 40-residue signal peptide. If that offset ever shifts,
# the viewer would highlight three arbitrary residues and call them the active
# site, which is the kind of confident-looking error this project exists to
# avoid. The build refuses rather than guesses.

def _pdb(residues: dict[int, str], chain: str = "A") -> str:
    lines = []
    for i, (resi, name) in enumerate(sorted(residues.items()), start=1):
        lines.append(
            f"ATOM  {i:5d}  CA  {name:>3} {chain}{resi:4d}"
            "      0.000   0.000   0.000  1.00  0.00           C"
        )
    return "\n".join(lines) + "\nTER\nEND\n"


def test_structure_build_accepts_the_verified_numbering(tmp_path):
    from tools import build_structure

    pdb = tmp_path / "ok.pdb"
    pdb.write_text(_pdb({130: "SER", 176: "ASP", 208: "HIS"}))
    assert build_structure.verify_triad(pdb) == {130: "SER", 176: "ASP", 208: "HIS"}


def test_structure_build_refuses_to_mislabel_the_active_site(tmp_path):
    from tools import build_structure

    # The same structure read one numbering scheme off: the positions exist but
    # hold different residues.
    pdb = tmp_path / "shifted.pdb"
    pdb.write_text(_pdb({130: "ALA", 176: "GLY", 208: "LEU"}))
    with pytest.raises(SystemExit) as exc:
        build_structure.verify_triad(pdb)
    assert "mislabel" in str(exc.value)


def test_structure_build_keeps_one_chain(tmp_path):
    from tools import build_structure

    src = tmp_path / "two_chains.pdb"
    src.write_text(
        _pdb({130: "SER"}, chain="A").replace("END\n", "")
        + _pdb({130: "SER"}, chain="B")
    )
    atoms = build_structure.trim(src, tmp_path / "out.pdb")
    assert atoms == 1, "chain B is a second copy, not more of the same molecule"
