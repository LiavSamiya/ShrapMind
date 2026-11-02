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
    from f2c import metals

    for key in metals.METALS:
        route = metals.route(key)
        for stage in route["stages"]:
            for cand in stage.get("candidates") or []:
                assert "not metallic" in cand["acts_on"] or "dissolved" in cand["acts_on"], (
                    f"{cand['name']} must state that it acts on the ion, not the metal"
                )


def test_a_two_stage_metal_puts_capture_after_dissolution_and_says_why():
    """Capture is stage 3 in the sequence and first in priority. The polymer
    arm catches what degradation releases; here the released ion is the hazard,
    so the route has to say that rather than imply a mirror image."""
    from f2c import metals

    steel = metals.route("steel")
    assert [s["n"] for s in steel["stages"]] == [1, 2, 3]
    assert steel["stages"][2]["stage"] == "Capture"
    assert "hazard" in steel["stages"][2]["why"]
    assert steel["warning"]["status"].startswith("inverts")


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
    assert "composite" in cu["reason"]


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
