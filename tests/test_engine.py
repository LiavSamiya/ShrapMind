"""Tests for the quality rules the product promises to enforce."""
from __future__ import annotations

import datetime as _dt
import json
import re
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


# --- the clinical layer's citations ----------------------------------------
# Two of the three original references did not support the claim they were
# attached to. That is not an unusual accident, it is what happens when
# citations are written from memory, so these tests make the shape of an
# honest citation enforceable rather than a habit.

def test_every_clinical_reference_carries_an_identifier_and_a_claim():
    from f2c.pipeline import REFS

    for key, ref in REFS.items():
        assert ref["pmid"].isdigit(), f"{key}: PMID must be numeric"
        assert ref["doi"].startswith("10."), f"{key}: DOI must be a real prefix"
        assert len(ref["says"]) > 60, (
            f"{key}: 'says' must state what the paper shows. A citation without "
            "it is the failure mode this field exists to prevent."
        )


def test_every_reference_is_actually_used_somewhere():
    """An unused reference is decoration, and decoration drifts out of date
    without anyone noticing it stopped being true."""
    import json

    from f2c.pipeline import REFS, build

    body = json.dumps(build("PET", ["terephthalate"]))
    for key, ref in REFS.items():
        assert ref["pmid"] in body, f"{key} is defined but cited by nothing"


def test_caveats_name_the_reference_they_are_correcting():
    from f2c.pipeline import CAVEATS

    assert CAVEATS, "the known gaps between brief and evidence must be listed"
    for c in CAVEATS:
        assert c["evidence"]["pmid"], "a caveat must point at the citation it corrects"
        assert len(c["detail"]) > 80, "a caveat has to say what the paper does show"
        assert c["status"], "a caveat must state how far the claim survives"


def test_the_indication_states_what_its_evidence_does_not_cover():
    """The lead-toxicity review justifies intervening on retained fragments.
    It says nothing about polymers, and the product must not let that slide."""
    from f2c.pipeline import indication

    ind = indication()
    assert ind["ref"]["pmid"] == "36074021"
    assert "honest_limit" in ind
    assert "lead" in ind["honest_limit"].lower()


# --- what success means ------------------------------------------------------
# The clinical problem is removal that beats surgery, and surgery loses on
# grounds other than completeness. These tests hold the line between a goal
# that genuinely lowers the bar and one that only looks like it does.

def test_debulking_is_not_blocked_by_a_ceiling_that_blocks_full_degradation():
    from f2c import goals

    full = goals.assess("full", crystallinity_pct=55.0, particle_size_mm=0.8)
    part = goals.assess("debulk", crystallinity_pct=55.0, particle_size_mm=0.8)
    assert full["ceiling"]["blocks"] is True
    assert part["ceiling"]["blocks"] is False
    assert part["ceiling"]["headroom_pct"] > 0


def test_the_ceiling_still_binds_when_the_amorphous_fraction_is_too_small():
    from f2c import goals

    tight = goals.assess("debulk", crystallinity_pct=85.0, particle_size_mm=0.8)
    assert tight["ceiling"]["blocks"] is True
    assert "regardless of how long" in tight["ceiling"]["note"]


def test_clearing_micro_fragments_does_not_lower_the_completeness_bar():
    """Micro mode improves the rate, through surface area. Letting it also
    inherit the partial target would hand it a feasibility it has not got."""
    from f2c import goals

    micro = goals.assess("micro", crystallinity_pct=55.0, particle_size_mm=0.1,
                         specific_area_mm2_per_mg=43.5)
    assert micro["target_pct"] == 100.0
    assert micro["ceiling"]["blocks"] is True
    assert micro["surface_advantage"]["specific_area_mm2_per_mg"] == 43.5


def test_debulking_carries_the_migration_warning():
    """The appealing version of this goal is that the fragment drifts clear.
    The literature documents migration as embolisation, so the warning travels
    with the mode rather than waiting to be remembered."""
    from f2c import goals

    part = goals.assess("debulk", crystallinity_pct=40.0, particle_size_mm=0.8)
    warnings = [w for w in part["warnings"]
                if "migration" in w["status"] or "migration" in w["detail"]]
    assert warnings, "debulk must warn that migration means embolisation"
    assert "embolisation" in warnings[0]["detail"]


def test_micro_mode_objects_when_the_fragments_are_not_small():
    from f2c import goals

    wrong = goals.assess("micro", crystallinity_pct=40.0, particle_size_mm=3.0)
    assert any("does not match the input" in w["status"] for w in wrong["warnings"])


def test_no_goal_claims_a_duration():
    """Every mode settles how much, never how fast. The interfacial rate is
    unmeasured, and a mode that implied a timeline would be the one place this
    engine overstated its evidence."""
    from f2c import goals

    for g in ("full", "debulk", "micro"):
        assessed = goals.assess(g, crystallinity_pct=40.0, particle_size_mm=0.3)
        assert "how fast" in assessed["rate_unknown"]


def test_smaller_fragments_present_more_surface_for_the_same_mass():
    """The arithmetic behind micro mode being the favourable case."""
    from f2c.formulate import geometry

    coarse = geometry("PET", 50.0, 2.0)["specific_area_mm2_per_mg"]
    fine = geometry("PET", 50.0, 0.1)["specific_area_mm2_per_mg"]
    assert fine > coarse * 10


def test_every_material_in_the_interface_has_a_full_name():
    """PBAT means nothing to a clinician. The abbreviation is how the
    literature is indexed; the name is how a person recognises the material,
    and the interface needs both for everything it offers."""
    from f2c import warehouse
    from f2c.export_ui import build, material_names

    proteins = warehouse.load()
    payload = build(proteins)
    names = material_names(proteins)
    missing = [k for k in payload["decisions"] if k not in names]
    assert not missing, f"materials shown with no full name: {missing}"


def test_material_names_prefer_the_source_database_over_the_local_table():
    from f2c import warehouse
    from f2c.export_ui import material_names

    names = material_names(warehouse.load())
    # PAZy's own wording, not something retyped here.
    assert names["PET"] == "Polyethylene terephthalate"
    assert names["PBAT"] == "Polybutylene adipate terephthalate"
    # And the ones PAZy never carried, because nothing degrades them.
    assert names["steel"] == "Steel"
    assert names["PE"] == "Polyethylene"


# --- the metal arm -----------------------------------------------------------
# "No enzyme degrades metal" was too short an answer. Enzymes act on metals by
# electron transfer; what none of them acts on is the metallic lattice. These
# tests hold that distinction, because collapsing it in either direction is how
# this arm would mislead.

def test_no_metal_route_claims_to_act_on_the_lattice():
    """The invariant, asserted negatively.

    An earlier version listed the two phrasings that were then in use, and
    broke when a candidate correctly said it acts on the oxide surface — a
    third right answer. Twice now a test of mine has failed on wording while
    the behaviour was fine, so this one states what must not be claimed
    instead of enumerating what may be.
    """
    from f2c import metals

    forbidden = ("metallic iron", "the lattice", "metallic lattice", "Fe(0)")
    allowed = ("dissolved", "oxide surface", "ion")
    for key in metals.METALS:
        for stage in metals.route(key)["stages"]:
            for cand in stage.get("candidates") or []:
                acts = cand["acts_on"]
                assert acts, f"{cand['name']} must say what it acts on"
                # "dissolved Fe(II), not metallic iron" is the correct
                # statement, so drop negated clauses before looking for a
                # claim. A bare substring match reads the disclaimer as the
                # claim it was written to deny.
                claimed = re.sub(r",?\s*\bnot\b[^,.;]*", "", acts)
                assert not any(f in claimed for f in forbidden), (
                    f"{cand['name']} claims to act on the metal itself: {acts!r}"
                )
                assert any(a in acts for a in allowed), (
                    f"{cand['name']} must name the ion or surface it acts on: {acts!r}"
                )


def test_a_two_stage_metal_puts_capture_after_dissolution_and_says_why():
    """Capture is stage 3 in the sequence and first in priority. The polymer
    arm catches what degradation releases; here the released ion is the hazard,
    so the route has to say that rather than imply a mirror image."""
    from f2c import metals

    steel = metals.route("steel")
    assert [s["n"] for s in steel["stages"]] == [1, 2, 3]
    assert steel["stages"][2]["stage"] == "Capture"
    # The route must explain the inversion somewhere, not merely order the
    # stages. Checked across the route rather than against one sentence.
    text = json.dumps(steel)
    assert "Inverted from the polymer arm" in text
    assert steel["warning"]["status"].startswith("inverts")


def test_dissolution_is_bounded_by_its_own_capture():
    """The answer to the arm's own warning. Chelation-driven dissolution
    proceeds only as fast as there is free chelator, so the accelerant and the
    capture agent are one molecule and the hazard is bounded by design."""
    from f2c import metals

    stage1 = metals.route("steel")["stages"][0]
    assert stage1["self_limiting"]
    assert "cannot run away" in stage1["self_limiting"]
    names = [c["name"] for c in stage1["candidates"]]
    assert any("eferoxamine" in n or "esferrioxamine" in n for n in names)


def test_nothing_claims_a_chelator_was_tested_on_metal():
    """PubMed returns nothing for a chelator against metallic iron. The route
    rests on the oxide layer a retained fragment already carries, and must say
    so rather than let the reader assume the metal case was covered."""
    from f2c import metals

    stage1 = metals.route("steel")["stages"][0]
    dfob = stage1["candidates"][0]
    gap = dfob["mismatch"][0]
    assert "goethite" in gap["measured"]
    assert "unmeasured" in gap["detail"]


def test_passivating_metals_have_no_route_and_name_the_reason():
    from f2c import metals

    for key in ("aluminium", "titanium", "tungsten"):
        route = metals.route(key)
        assert route["route"] == "none"
        assert not route["stages"]
        assert route["why_not"], f"{key} must say why, not just refuse"


def test_lead_gets_capture_without_a_dissolution_stage():
    """Lead has no biological redox couple, so there is nothing to catalyse.
    Offering it an enzyme stage would be inventing one."""
    from f2c import metals

    lead = metals.route("lead")
    assert lead["route"] == "capture_only"
    assert len(lead["stages"]) == 1
    assert not lead["stages"][0].get("candidates")


def test_the_iron_enzyme_declares_its_five_unit_pH_gap():
    """Cyc2 comes from an organism that lives at pH 2. That gap is the whole
    engineering problem and must travel with the candidate."""
    from f2c import metals

    cyc2 = metals.ENZYMES["cyc2"]
    ph = [m for m in cyc2["mismatch"] if m["kind"] == "pH"]
    assert ph and "pH 2" in ph[0]["measured"]
    assert ph[0]["target"] == "pH 7.4"


def test_iron_engineering_includes_the_option_of_abandoning_the_enzyme():
    """At pH 7.4 Fe(II) autoxidises in minutes. If the uncatalysed rate already
    beats the enzyme, the enzyme is the wrong component — and a plan that
    cannot reach that conclusion is advocacy, not engineering.

    Asserted on the reasoning rather than on the heading, because the heading
    has already been rewritten once: this test caught the rewrite and should
    not have, since the target survived it under another name.
    """
    from f2c import metals

    targets = metals.engineering_targets("steel")
    assert any("autoxidises" in t["detail"] and "uncatalysed" in t["detail"]
               for t in targets), (
        "the plan must be able to conclude that the enzyme is unnecessary"
    )


def test_the_iron_lead_is_human_and_stores_what_it_oxidises():
    """Querying EC 1.16.3 beat recalling the literature. Cyc2 needs five pH
    units of engineering; human ferritin already oxidises Fe(II) and keeps the
    product inside its own shell at cytosolic pH."""
    from f2c import metals

    lead = metals.rank_candidates("Fe")[0]
    assert lead["accession"] == "P02794"
    assert lead["human"] is True
    assert lead["stores_as_well_as_oxidises"] is True
    assert lead["structures"] > 100


def test_copper_does_not_inherit_the_iron_candidates():
    """Ferritin is not a copper enzyme. An earlier version widened the class
    filter and handed every ferritin back as a copper answer."""
    from f2c import metals

    cu = {c["accession"] for c in metals.rank_candidates("Cu")}
    assert "P02794" not in cu, "ferritin must not appear in a copper answer"
    assert "P00450" in cu, "ceruloplasmin spans both metals and belongs here"


def test_every_ranked_candidate_is_reviewed_and_unmeasured():
    """These came from Swiss-Prot by EC class, not from a curated activity
    list. None has been tested against a fragment, and the module must not
    acquire a score that implies otherwise."""
    from f2c import metals

    for element in ("Fe", "Cu"):
        for c in metals.rank_candidates(element):
            assert "score" not in c
            assert c["accession"] and c["organism"]


def test_metal_aliases_resolve_the_words_a_clinician_would_write():
    from f2c import metals

    assert metals.resolve("Fe") == "iron"
    assert metals.resolve("carbon steel") == "steel"
    assert metals.resolve("brass") == "copper"
    assert metals.resolve("aluminum") == "aluminium"
    assert metals.resolve("PET") is None


def test_metal_capacity_is_derived_and_scales_linearly():
    """Same discipline as the polymer arm: capacity from mass, rate refused.
    Linearity matters because a rounding bug there once destroyed it."""
    from f2c import metals

    small = metals.capacity("steel", 10.0)
    large = metals.capacity("steel", 1000.0)
    assert small["computable"] and large["computable"]
    assert abs(large["ferritin_mg"] / small["ferritin_mg"] - 100.0) < 0.01
    assert abs(small["ratio_to_fragment"] - large["ratio_to_fragment"]) < 1e-6
    assert "Not derivable" in large["rate"]


def test_metal_capacity_refuses_a_composite_fragment():
    """A jacketed fragment's copper fraction depends on the round. Guessing it
    would be the one invented number in the arm."""
    from f2c import metals

    cu = metals.capacity("copper", 50.0)
    assert cu["computable"] is False
    assert "composite" in cu["why"]


def test_capacity_names_its_one_assumption_and_bounds_it():
    """Atoms per shell is the only figure here that is not derived, so it has
    to be labelled and a pessimistic case shown beside it."""
    from f2c import metals

    cap = metals.capacity("steel", 50.0)
    assert "assumed rather than derived" in cap["assumption"]
    worst = min(cap["sensitivity"], key=lambda s: s["atoms_per_shell"])
    assert worst["ferritin_mg"] > cap["ferritin_mg"]


def test_the_metal_carrier_states_why_it_matters_more_than_in_the_polymer_arm():
    """Ferritin is cytosolic and the fragment is extracellular, so the gel is
    the only contact between them rather than a delivery convenience."""
    from f2c import metals

    carrier = metals.route("steel")["carrier"]
    holds = [c for c in carrier if "surface" in c["property"]]
    assert holds and "cytosolic" in holds[0]["why"]
    assert any("swell" in c["property"].lower() for c in carrier), (
        "non-swelling is still the property most likely to end the programme"
    )


def test_the_arm_answers_what_happens_to_unrusted_metal():
    """Every candidate acts on the oxide, which invites the obvious objection
    that the metal underneath is untouched.

    The invariant, not the wording: the arm must distinguish iron from the
    metals whose oxide really does protect them, must explain how the metal is
    consumed indirectly, and must concede that oxide still accumulates. An
    earlier version of this test asserted the literal phrase "does not
    passivate" and failed when that claim was deliberately softened -- the
    team's clinical review is right that oxidising Fe(II) produces oxides that
    slow the reaction, so "does not passivate" was too absolute. The test was
    wrong about what it was protecting.
    """
    from f2c import metals

    u = metals.route("steel")["unrusted_metal"]
    cycle = u["cycle"].lower()
    # Iron is treated differently from the self-healing oxides, by name.
    assert "aluminium" in cycle and "titanium" in cycle
    # And the mechanism is indirect consumption, not attack on the lattice.
    assert "lattice" in cycle
    assert re.search(r"re-?oxidis", cycle), (
        "the strip-reoxidise-strip cycle is the whole argument for iron"
    )
    # The concession has to be present too: a poor passivating layer is not no
    # passivating layer, and the arm must say so rather than overclaim.
    assert u.get("but_not_nothing"), (
        "the arm must concede that oxide accumulation slows the reaction"
    )
    assert "slow" in u["but_not_nothing"].lower()
    # Aluminium and titanium themselves must stay excluded.
    for metal in ("aluminium", "titanium"):
        assert metals.METALS[metal]["route"] == "none"

def test_the_arm_corrects_its_own_runaway_warning():
    """The arm warns that dissolution could run away into systemic exposure.
    The biodegradable-implant literature says iron corrodes too slowly in the
    body for its intended purpose, so the engineering problem is the opposite.
    Both have to be present: the safety concern stands, the priority flips."""
    from f2c import metals

    route = metals.route("steel")
    assert route["warning"]["status"].startswith("inverts")
    assert "too slowly" in route["unrusted_metal"]["the_real_bottleneck"] or \
           "corrode at all" in route["unrusted_metal"]["the_real_bottleneck"]


def test_passivating_metals_are_excluded_for_the_reason_iron_works():
    """The same property decides both: iron's oxide flakes and exposes metal,
    aluminium's and titanium's heal over. One sentence should not be able to
    drift from the other."""
    from f2c import metals

    assert "non-passivating" in metals.METALS["steel"]["oxide"]
    for key in ("aluminium", "titanium"):
        assert "passivating" in metals.METALS[key]["oxide"]
        assert metals.METALS[key]["route"] == "none"


def test_debulking_and_consumption_differ_by_the_cube_of_the_dimension():
    """The geometric fact that decides which goals survive. Volume goes as the
    cube, so a fifth of it costs 3.6% of the edge where all of it costs 50% —
    a factor of fourteen, and the difference between decades and months."""
    from f2c.metals import _penetration_fraction

    assert _penetration_fraction(1.0) == 0.5
    part = _penetration_fraction(0.20)
    assert 0.03 < part < 0.04
    assert 13 < 0.5 / part < 15


def test_the_timeline_says_which_goals_survive_it():
    """Reporting the numbers without the conclusion would let a reader take
    'we can dissolve shrapnel' from a table that says the opposite."""
    from f2c import metals

    f = metals.feasibility_by_goal("steel", 0.8)
    assert f["full"]["verdict"] == "not a clinical timescale"
    assert f["debulk_20pct"]["verdict"] == "clinically plausible"
    assert f["full"]["years_at_demonstrated_rate"] > 2
    assert f["debulk_20pct"]["months_at_demonstrated_rate"] < 18


def test_the_timeline_names_what_the_rates_do_not_include():
    """Every rate is iron corroding alone. What a chelator adds is the gap, and
    a constant rate is the optimistic reading rather than the cautious one."""
    from f2c import metals

    tl = metals.timeline("steel", 0.8)
    assert "nobody has measured chelation against metallic" in tl["what_is_unmeasured"]
    assert "optimistic" in tl["caveat"]


# --- the carrier arithmetic -------------------------------------------------
# Both of these come from reviewing a teammate's hydrogel architecture, which
# supplied the carrier this arm had only specified as a requirement. Neither
# number was in that document; both are arithmetic over numbers that were.

def test_chelator_demand_is_stoichiometric_not_an_estimate():
    """DFO binds Fe(III) 1:1, so doubling the iron doubles the chelator."""
    from f2c import metals
    a = metals.chelator_demand("steel", 50.0, 0.20)
    b = metals.chelator_demand("steel", 100.0, 0.20)
    assert a["computable"] and b["computable"]
    assert b["dfo_free_base_mg"] == pytest.approx(2 * a["dfo_free_base_mg"])
    # The ratio is a property of the two molar masses, not of the fragment.
    assert a["mg_dfo_per_mg_iron"] == pytest.approx(b["mg_dfo_per_mg_iron"])
    assert a["mg_dfo_per_mg_iron"] > 1, (
        "the chelator must outweigh the iron it carries; if this inverts, the "
        "molar masses have been swapped"
    )


def test_chelator_demand_refuses_metals_dfo_does_not_bind():
    """DFO is selective for Fe(III). Saying so is the point of the refusal."""
    from f2c import metals
    for metal in ("copper", "lead", "tungsten"):
        out = metals.chelator_demand(metal, 50.0)
        assert out["computable"] is False, f"{metal} must not get an iron answer"
        assert "why" in out and out["why"]


def test_carrier_placements_divides_timeline_by_carrier_life():
    """The dosing schedule neither input states on its own."""
    from f2c import metals
    out = metals.carrier_placements("steel", 0.8, 0.20)
    assert out["computable"]
    # A longer-lived carrier can only need fewer placements.
    longer = metals.carrier_placements("steel", 0.8, 0.20, carrier_weeks=16.0)
    for slow, fast in zip(out["rows"], longer["rows"]):
        assert fast["placements"] <= slow["placements"]
    # Slower corrosion cannot need fewer placements than faster corrosion.
    by_rate = sorted(out["rows"], key=lambda r: r["rate_mm_per_year"])
    counts = [r["placements"] for r in by_rate]
    assert counts == sorted(counts, reverse=True)


def test_carrier_placements_names_the_marginal_case():
    """A rate landing days past the carrier's life is one dose, not two.

    Rounding it up would be arithmetic presented as a finding, which is the
    failure this whole engine exists to avoid.
    """
    from f2c import metals
    out = metals.carrier_placements("steel", 0.8, 0.20)
    covered = set(out["single_dose_cases"]) | set(out["marginal_cases"])
    assert covered & {"accelerated_9x"}, (
        "the fastest demonstrated rate completes a 20% debulk within about one "
        "carrier lifetime and must not be reported as needing repeat dosing"
    )
    assert "pure_iron_low" in out["repeat_dose_cases"]
    # Every row lands in exactly one bucket.
    buckets = (out["single_dose_cases"] + out["marginal_cases"]
               + out["repeat_dose_cases"])
    assert sorted(buckets) == sorted(r["label"] for r in out["rows"])


def test_reference_keys_are_unique():
    """A duplicated REFS key silently overwrites the first entry.

    There were two identical `ligand_dissolution` entries in metals.py. They
    happened to carry the same content, so nothing was lost -- but a table
    where a repeated key is harmless is a table where a repeated key with
    different content would be invisible.
    """
    import ast
    import pathlib
    for name in ("metals.py", "pipeline.py"):
        src = pathlib.Path(__file__).resolve().parent.parent / "f2c" / name
        tree = ast.parse(src.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not any(getattr(x, "id", None) == "REFS" for x in node.targets):
                continue
            keys = [k.value for k in node.value.keys
                    if isinstance(k, ast.Constant)]
            dupes = {k for k in keys if keys.count(k) > 1}
            assert not dupes, f"{name} REFS has duplicate key(s): {dupes}"


# --- the host-safety screen -------------------------------------------------
# This existed as prose on the safety review page, which stated it was "now a
# gate" and that host-unsafe candidates "sort last at retrieval". Neither was
# true: nothing in rank.py knew about host substrates. These tests are what
# makes the claim true.

def test_peptidases_are_refused_on_their_own_class():
    from f2c import hostsafety, warehouse
    by_name = {p.name: p for p in warehouse.load()}
    for name in ("Proteinase K", "Subtilisin Carlsberg", "Subtilisin Savinase"):
        v = hostsafety.screen(by_name[name])
        assert v["severity"] == hostsafety.BLOCKING, name
        assert v["basis"].startswith("EC 3.4")


def test_a_missing_ec_number_does_not_mean_a_missing_flag():
    """The warehouse holds entries named only "protease", with no EC at all."""
    from f2c import hostsafety, warehouse
    nameless = [p for p in warehouse.load()
                if not p.ec_numbers
                and "protease" in (p.name or "").lower()]
    assert nameless, "fixture gone: expected unclassified protease entries"
    for p in nameless:
        v = hostsafety.screen(p)
        assert v["severity"] == hostsafety.BLOCKING, p.name
        assert v["basis"] == "name"


def test_no_flag_is_reported_as_an_absence_not_as_safety():
    """The 457 enzymes the screen says nothing about must not read as clear.

    Drawn from the warehouse rather than invented, because an invented EC
    number proves only that the string matching works. A first draft of this
    test used Cutinase, which is EC 3.1.1.74 and therefore a carboxylic-ester
    hydrolase the screen rightly puts under caution -- the test was wrong and
    the screen was right.
    """
    from f2c import hostsafety, warehouse
    unflagged = [p for p in warehouse.load()
                 if hostsafety.screen(p)["severity"] == hostsafety.UNFLAGGED]
    assert unflagged, "fixture gone: expected unflagged entries"
    for protein in unflagged[:40]:
        v = hostsafety.screen(protein)
        assert v["is_screened"] is False, (
            f"{protein.name} reads as screened-and-clear"
        )
        assert "not evidence of selectivity" in v["statement"]
        assert v["host_substrate"] is None


def test_an_esterase_is_cautioned_not_cleared():
    """Cutinase acts on esters, and host tissue is full of them."""
    from f2c import hostsafety
    v = hostsafety.screen_reagent("Cutinase", ["3.1.1.74"])
    assert v["severity"] == hostsafety.CAUTION
    assert v["basis"] == "EC 3.1.1"
    # And the longest prefix wins, so a lipase is not merely an esterase.
    lip = hostsafety.screen_reagent("CalB", ["3.1.1.3"])
    assert lip["severity"] == hostsafety.SERIOUS
    assert lip["basis"] == "EC 3.1.1.3"


def test_the_screen_reaches_reagents_outside_the_warehouse():
    """Stage 0 proposes collagenase, which the warehouse has never heard of."""
    from f2c import hostsafety
    v = hostsafety.screen_reagent(
        "Collagenase clostridium histolyticum", ["3.4.24.3"])
    assert v["severity"] == hostsafety.BLOCKING
    assert "collagen" in v["host_substrate"].lower()
    listed = {r["name"]: r for r in hostsafety.PROPOSED_REAGENTS}
    assert any("Collagenase" in n for n in listed), (
        "a reagent proposed in a team document must be screened here, or the "
        "proposal and the screen drift apart"
    )


def test_refused_candidates_sort_below_every_unflagged_one():
    """The gate, stated as an order rather than as a discount.

    Proteinase K scores highest in the PLA pool on evidence strength. It must
    still sort below candidates that score worse and are not refused, because
    digesting host tissue is a different kind of answer from being slow.
    """
    from f2c import hostsafety, rank, retrieve, schema, warehouse
    pool = retrieve.retrieve(schema.MaterialSpec(polymer="PLA"),
                             warehouse.load()).candidates
    ranked = rank.rank(pool)
    severities = [hostsafety.screen(c.protein)["severity"] for c in ranked]
    worst_unflagged = max(i for i, s in enumerate(severities)
                          if s == hostsafety.UNFLAGGED)
    first_blocking = min((i for i, s in enumerate(severities)
                          if s == hostsafety.BLOCKING), default=None)
    assert first_blocking is not None, "fixture gone: PLA had refused candidates"
    assert first_blocking > worst_unflagged, (
        "a refused candidate outranked an unflagged one"
    )
    refused = ranked[first_blocking]
    assert any(r.startswith("REFUSED on host safety") for r in refused.reasons)
    # And the refusal must not be achieved by hiding it from the pool.
    assert len(ranked) == len(pool)


def test_screen_counts_partition_the_warehouse():
    from f2c import hostsafety, warehouse
    s = hostsafety.summary(warehouse.load())
    assert sum(s["counts"].values()) == s["total"]
    assert s["counts"][hostsafety.BLOCKING] > 0


# --- sentinel values --------------------------------------------------------

def test_no_sentinel_values_reach_the_warehouse():
    """BRENDA writes -999 where a qualitative entry replaces a number.

    Twenty-four of them were being carried as measurements, including a
    temperature optimum of -999 C that inflated Proteinase K's measured spread
    from 47 degrees to 1069 and collapsed the confidence term in its
    temperature fit. A project that refuses unprovenanced numbers was
    averaging a missing-value marker into its own scores.
    """
    from f2c import warehouse
    from f2c.sources import brenda
    offenders = [
        (p.name, o.metric, o.value)
        for p in warehouse.load() for o in p.observations
        if isinstance(o.value, (int, float))
        and o.value in brenda.SENTINEL_VALUES
    ]
    assert not offenders, f"sentinel values in the warehouse: {offenders[:5]}"


def test_sentinels_are_dropped_rather_than_substituted():
    """There is no measurement to represent, so none is invented."""
    from f2c.sources import brenda
    value, substrate = brenda._parse_value("-999 {more}")
    assert value is None
    assert substrate == "more", (
        "the substrate annotation is still worth keeping; only the number goes"
    )
    assert brenda._parse_value("3.81 {4-nitrophenyl octanoate}")[0] == 3.81


def test_published_pages_do_not_contradict_the_engine():
    """Run the cross-page consistency check as part of the suite.

    The safety review was written on 2026-10-27 with correct figures. By
    2026-11-02 the ranking had changed twice, a substrate classifier had been
    added and 24 sentinel values had been removed -- and the page still stated
    the October numbers, which looked exactly as authoritative as current ones.
    A checker nobody runs is a checker that catches nothing.
    """
    from tools import verify_consistency as vc
    d = vc._engine()
    stale = []
    for check in vc.CHECKS:
        truth = check["truth"](d)
        claimed = check["claimed"]
        ok = (abs(claimed - truth) < 0.02
              if isinstance(claimed, float) and isinstance(truth, (int, float))
              else claimed == truth)
        if not ok:
            stale.append(f"{check['page']}: {check['what']} "
                         f"(page {claimed}, engine {truth})")
    assert not stale, "pages state figures the engine contradicts: " + "; ".join(stale)


def test_the_built_safety_review_has_no_unfilled_tokens():
    from pathlib import Path
    import re
    built = Path(__file__).resolve().parent.parent / "ui" / "safety-review.html"
    assert built.exists(), "run `python -m tools.build_safety_review`"
    left = re.findall(r"\{\{[A-Z_]+\}\}", built.read_text())
    assert not left, f"unsubstituted tokens in the published page: {set(left)}"


# --- the pH-site screen -----------------------------------------------------

def test_only_residues_whose_pka_is_inside_the_span_respond():
    """A side chain responds to a pH move only if its pKa lies between the two.

    Asp at 3.9 and Arg at 12.5 are fully ionised at both ends of the
    physiological span, so a pH 8 to 7.4 move changes nothing for them.
    Histidine at 6.0 is the residue that actually switches.
    """
    from f2c import phsites
    asp = phsites.charged_fraction(3.9, 8.0, "deprotonated")
    asp_t = phsites.charged_fraction(3.9, 7.4, "deprotonated")
    his = phsites.charged_fraction(6.0, 6.0, "protonated")
    assert abs(asp - asp_t) < 0.01, "Asp must not register as pH-responsive here"
    assert abs(his - 0.5) < 0.01, "at its own pKa a residue is half charged"
    # And the direction is right: a base is less protonated as pH rises.
    assert (phsites.charged_fraction(6.0, 5.0, "protonated")
            > phsites.charged_fraction(6.0, 8.0, "protonated"))


def test_the_catalytic_histidine_leads_the_shortlist():
    from pathlib import Path
    from f2c import phsites
    pdb = Path(__file__).resolve().parent.parent / "data/raw/structures/4cg1_trimmed.pdb"
    if not pdb.exists():
        import pytest as _p
        _p.skip("structure not built; run tools/build_structure.py")
    r = phsites.analyse(pdb, site_residues=[130, 176, 208],
                        pH_from=8.0, pH_to=7.4)
    assert not r["site_residues_missing_from_structure"]
    assert r["shortlist"][0]["residue"] == "HIS208"
    assert r["shortlist"][0]["is_catalytic"] is True


def test_proximity_is_measured_from_the_ionisable_group_not_the_backbone():
    """Every residue's backbone touches its sequence neighbour's.

    Measuring all atoms put His129 1.33 A from Ser130 -- a peptide bond, not a
    functional proximity -- and shortlisted it for being adjacent in sequence.
    """
    from pathlib import Path
    from f2c import phsites
    pdb = Path(__file__).resolve().parent.parent / "data/raw/structures/4cg1_trimmed.pdb"
    if not pdb.exists():
        import pytest as _p
        _p.skip("structure not built")
    r = phsites.analyse(pdb, site_residues=[130, 176, 208])
    his129 = next(x for x in r["rows"] if x["residue"] == "HIS129")
    assert his129["distance_to_site_a"] > 2.0, (
        "a sequence neighbour must not read as a bond length away"
    )


def test_a_wide_ph_move_changes_far_more_than_a_narrow_one():
    """The acidophile problem, quantified rather than asserted.

    The arm says Cyc2 carries a five-pH-unit gap. Moving a structure from pH 2
    to 7.4 must flip many more residues than moving it from 8 to 7.4, including
    the catalytic acid.
    """
    from pathlib import Path
    from f2c import phsites
    pdb = Path(__file__).resolve().parent.parent / "data/raw/structures/4cg1_trimmed.pdb"
    if not pdb.exists():
        import pytest as _p
        _p.skip("structure not built")
    narrow = phsites.analyse(pdb, [130, 176, 208], pH_from=8.0, pH_to=7.4)
    wide = phsites.analyse(pdb, [130, 176, 208], pH_from=2.0, pH_to=7.4)
    assert wide["responsive_in_span"] > 3 * narrow["responsive_in_span"]
    asp = next(x for x in wide["rows"] if x["residue"] == "ASP176")
    assert asp["ionisation_change"] > 0.9, (
        "the catalytic aspartate inverts its charge across this span"
    )


def test_pi_is_computed_and_flags_proximity_to_body_ph():
    from f2c import phsites, warehouse
    seq = {p.name: p for p in warehouse.load()}["TfH"].sequence
    out = phsites.isoelectric_point(seq)
    assert 3.0 < out["pI"] < 12.0
    # TfH's pI sits close to 7.4, which is a formulation finding rather than a
    # catalytic one, and the function must say so.
    assert out["aggregation_risk_near_pI"] is True
    assert abs(out["pI"] - 7.4) < 1.0


# --- the DNA construct ------------------------------------------------------

def test_the_construct_translates_back_to_the_designed_protein():
    """Reverse translation is mechanical, so this must be exact.

    Checked against a standard codon table built here, not against the tool's
    own table, since round-tripping through one table proves nothing.
    """
    from tools.design_construct import (CODONS, STOP, TAGS, reverse_translate)
    bases, aas = "TCAG", (
        "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG")
    std = {}
    i = 0
    for a in bases:
        for b in bases:
            for c in bases:
                std[a + b + c] = aas[i]
                i += 1
    # Every codon the tool can emit must mean what the tool thinks it means.
    for aa, codons in CODONS.items():
        for codon in codons:
            assert std[codon] == aa, f"{codon} is {std[codon]}, not {aa}"
    assert all(std[STOP[i:i + 3]] == "*" for i in range(0, len(STOP), 3))

    from f2c import warehouse
    seq = {p.name: p for p in warehouse.load()}["TfH"].sequence[40:]
    prefix = "ATG" + TAGS["his6_n"]["dna"]
    body, _ = reverse_translate(seq, prefix=prefix)
    orf = prefix + body + STOP
    protein = "".join(std[orf[i:i + 3]] for i in range(0, len(orf) - 2, 3))
    assert protein.split("*")[0] == "M" + TAGS["his6_n"]["protein"] + seq
    assert len(orf) % 3 == 0


def test_the_construct_carries_no_internal_restriction_site():
    """Methionine and tryptophan have one codon each, so a site completed by
    ATG or TGG can only be fixed by changing the codon before it. Greedy
    selection alone produced an ORF with internal NdeI and NcoI sites."""
    from f2c import warehouse
    from tools.design_construct import (RESTRICTION, STOP, TAGS, _violates,
                                        reverse_translate, revcomp)
    seq = {p.name: p for p in warehouse.load()}["TfH"].sequence[40:]
    prefix = "ATG" + TAGS["his6_n"]["dna"]
    body, _ = reverse_translate(seq, prefix=prefix)
    orf = prefix + body + STOP
    assert not _violates(orf), f"constraints violated: {_violates(orf)}"
    for name, site in RESTRICTION.items():
        assert site not in orf and revcomp(site) not in orf, name


def test_a_mutation_written_against_wrong_numbering_is_refused():
    """The commonest way a construct fails, and it fails after it is paid for."""
    import pytest as _p
    from f2c import warehouse
    from tools.design_construct import apply_mutations
    seq = {p.name: p for p in warehouse.load()}["TfH"].sequence
    # Correct: structure numbering plus the 40-residue signal peptide.
    out, applied = apply_mutations(seq, ["H208A"], offset=40)
    assert applied[0]["uniprot_position"] == 248
    assert out[247] == "A" and seq[247] == "H"
    # Wrong: the same mutation read as UniProt numbering.
    with _p.raises(SystemExit):
        apply_mutations(seq, ["H208A"], offset=0)
    # And a position past the end.
    with _p.raises(SystemExit):
        apply_mutations(seq, ["H9999A"], offset=40)


def test_the_mutant_differs_from_wild_type_at_exactly_one_position():
    from f2c import warehouse
    from tools.design_construct import apply_mutations
    seq = {p.name: p for p in warehouse.load()}["TfH"].sequence
    mutant, _ = apply_mutations(seq, ["H208A"], offset=40)
    diffs = [i for i, (a, b) in enumerate(zip(seq, mutant)) if a != b]
    assert diffs == [247]


# --- what the clinical review corrected -------------------------------------

def test_the_arm_no_longer_claims_only_a_biofilm_attacks_metallic_iron():
    """It said so in plain words, and the team's clinical review disproved it.

    Tsurumaru 2018 shows a secreted [NiFe] hydrogenase oxidising Fe(0) on
    contact; Deutzmann 2015 shows cell-free spent medium doing it. A secreted
    protein acting on solid metal is the one step this arm could not fill.
    """
    from f2c import metals
    direct = metals.route("steel")["direct_attack"]
    names = [e["name"] for e in direct["enzymes"]]
    assert any("NiFe" in n for n in names)
    assert any("Cell-free" in n for n in names)
    pmids = {e["ref"]["pmid"] for e in direct["enzymes"] if e.get("ref")}
    assert {"30310166", "25900658"} <= pmids
    # An enzyme the project cannot cite must carry no reference rather than an
    # invented one.
    unreferenced = [e for e in direct["enzymes"] if not e.get("ref")]
    assert unreferenced and "FeFe" in unreferenced[0]["name"]
    # And the old claim must be gone from the alternative section.
    alt = metals.route("steel")["alternative"]
    assert "wrong about that" in alt["why_not_used"]


def test_the_hydrogen_the_route_would_release_is_computed():
    """One mole of H2 per mole of Fe(0), inside a closed capsule.

    Neither the clinical review nor the carrier document states this, and it
    follows from the reaction both cite.
    """
    from f2c import metals
    h = metals.hydrogen_evolution("steel", 50.0, 0.20)
    assert h["computable"]
    # Millilitres, not microlitres: the number is what makes it a problem.
    assert 3.0 < h["h2_ml_at_37c"] < 6.0
    # Stoichiometry is 1:1, so the volume scales with the iron.
    full = metals.hydrogen_evolution("steel", 50.0, 1.0)
    assert full["h2_ml_at_37c"] == pytest.approx(h["h2_ml_at_37c"] * 5, rel=1e-6)
    # And it is specific to iron.
    assert metals.hydrogen_evolution("lead", 50.0)["computable"] is False


def test_lead_distinguishes_detoxification_from_shrinkage():
    """The most inviting error in this arm: real enzymes, real products, and
    no effect on the thing the patient came in with."""
    from f2c import metals
    pb = metals.METALS["lead"]
    assert pb["route"] == "capture_only"
    text = pb["but_there_is_a_pathway"]
    assert "DETOXIFICATION IS NOT SHRINKAGE" in text
    assert "pyromorphite" in text.lower()
    assert pb["the_one_metallic_lead_precedent"]


def test_an_injected_oxidoreductase_has_clinical_precedent():
    """The question the ferroxidase arm could not answer before."""
    from f2c import metals
    # Classified as data, not matched on the product name: "uricase" is an
    # oxidase and the string does not say so.
    oxidases = [p for p in metals.CLINICAL_PRECEDENTS
                if p["enzyme_class"] == "oxidoreductase"]
    assert len(oxidases) >= 2
    assert {"ELITEK", "KRYSTEXXA"} <= {p["product"] for p in oxidases}
    # Every precedent must state its limitation as well as what it proves.
    for p in metals.CLINICAL_PRECEDENTS:
        assert p["proves"] and p["but"], p["product"]
        assert p["enzyme_class"], p["product"]
    assert metals.clinical_precedent("local")
    assert all(p["locality"] == "local"
               for p in metals.clinical_precedent("local"))


def test_the_built_protocol_has_no_unfilled_tokens():
    from pathlib import Path
    import re
    built = Path(__file__).resolve().parent.parent / "ui" / "protocol.html"
    assert built.exists(), "run `python -m tools.build_protocol`"
    text = built.read_text()
    assert not re.findall(r"\{\{[A-Z_]+\}\}", text)
    # The sequence has to actually be in the page, not described.
    assert "ATGCATCATCATCATCATCAC" in text, (
        "the construct the protocol is about must appear in it"
    )


def test_the_protocol_does_not_claim_a_settled_temperature_optimum():
    """TfH's four reported optima are 25, 25, 50 and 55 -- a median of 37.5.

    A draft of the protocol asserted that TfH's problem was temperature rather
    than pH. The warehouse does not support that, and the page now states the
    scatter instead. This test exists because the claim was written and had to
    be caught.
    """
    from pathlib import Path
    from f2c import warehouse
    prot = {p.name: p for p in warehouse.load()}["TfH"]
    vals = sorted(o.value for o in prot.observations
                  if o.metric == "temperature_optimum_c" and o.value)
    assert len(vals) > 1 and max(vals) - min(vals) > 20, (
        "fixture gone: this test is about a disagreeing literature"
    )
    page = (Path(__file__).resolve().parent.parent / "ui" / "protocol.html").read_text()
    assert ", ".join(f"{v:g}" for v in vals) in page, (
        "the page must show every reported optimum, not pick one"
    )


# --- carbon steel is not stainless steel ------------------------------------

def test_stainless_is_a_separate_material_with_no_route():
    """The engine treated "steel" as one material. It is two.

    Above about 10.5% chromium the alloy grows a dense, self-healing Cr2O3
    film -- the aluminium and titanium behaviour this arm excludes, not the
    flaking rust it depends on. Ball bearings packed into a device are often
    stainless, so this is not an edge case.
    """
    from f2c import metals
    assert metals.METALS["stainless"]["route"] == "none"
    assert metals.METALS["steel"]["route"] == "two_stage"
    assert metals.METALS["stainless"]["element"] == "Fe", (
        "stainless is iron; the refusal must rest on passivation, not on "
        "the element"
    )
    reason = metals.METALS["stainless"]["no_enzyme_reason"].lower()
    assert "chromium" in reason and "passivat" in reason
    # And steel must now say which steel it means.
    assert "stainless" in metals.METALS["steel"]["which_steel"].lower()


def test_the_words_a_clinician_would_use_resolve_correctly():
    from f2c import metals
    for word in ("stainless steel", "316L", "ball bearing", "surgical steel",
                 "inox"):
        assert metals.resolve(word) == "stainless", word
    for word in ("mild steel", "carbon steel"):
        assert metals.resolve(word) == "steel", word


def test_no_quantity_is_computed_for_a_metal_with_no_route():
    """Iron content is not the question.

    chelator_demand happily returned a DFO mass for stainless, because it
    checked the element and not the verdict. Arithmetic answering a question
    the chemistry has already closed is exactly the failure this engine is
    built to refuse.
    """
    from f2c import metals
    for fn, args in (("capacity", ("stainless", 50.0)),
                     ("chelator_demand", ("stainless", 50.0)),
                     ("hydrogen_evolution", ("stainless", 50.0)),
                     ("timeline", ("stainless", 0.8)),
                     ("carrier_placements", ("stainless", 0.8))):
        out = getattr(metals, fn)(*args)
        assert out["computable"] is False, f"{fn} answered for stainless"
        assert out["why"], f"{fn} refused without saying why"
    # The same calls must still work for carbon steel.
    assert metals.chelator_demand("steel", 50.0, 0.20)["computable"]
    assert metals.hydrogen_evolution("steel", 50.0, 0.20)["computable"]
