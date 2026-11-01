"""The gate battery. Each gate must fire on the condition it exists for."""
import engines as E
import pytest

_RX = {"bond_class": "beta-1,4-glycosidic", "mechanism": "hydrolysis",
       "products": ["cellobiose"], "forbidden_products": ["microparticle", "formaldehyde"]}
# A "sound run" passport now also has to answer the comparator question: this
# approach is measured against forceps, not against doing nothing.
_PP = {"material_family": "cellulose", "anatomy_class": "soft_tissue",
       "confidence": 0.8, "presentation": "single_fragment",
       "retrievable_mechanically": False}
# A "sound run" fixture now has to state what its kinetics were measured on.
# Provenance "polymer" is the hypothetical case the knowledge base does not yet
# contain anywhere - which is exactly why the gate exists.
_BASE = {"k_cat": 3.0, "k_m_uM": 45.0, "half_life_h": 96.0, "volume_mm3": 8.0,
         "accessibility": 0.3, "mesh_nm": 20.0, "capture_rate_per_h": 0.6,
         "capture_capacity_umol": 200.0, "molar_mass_g_mol": 162.14,
         "density_g_cm3": 1.5, "kinetics_provenance": "polymer",
         "measured_on": "amorphous PET film",
         # A sound run also has to have ASKED whether the enzyme attacks the
         # patient. An unscreened candidate fails gate 15 by design.
         "enzyme_safety": {"name": "a clean esterase", "risks": [],
                           "worst_severity": "note", "blocking": False}}
_CAND = {"name": "cellulase-WT", "parent_family": "cellulase", "edits": []}


def _assay(**base_over):
    return E.simulate_hydrogel_assay(_CAND, {**_BASE, **base_over},
                                     {"hours": 336.0}, product="cellobiose",
                                     n_samples=32, seed=5)


def _gate(result, name):
    return next(g for g in result["gates"] if g["name"] == name)


def test_a_sound_run_passes_every_gate_except_unresolved_hazard():
    """With the chemistry snapshot unresolved - which is its committed state,
    because GHS codes are regulatory strings that must be fetched and must
    never be hand-entered - the hazard gate is the one that legitimately
    fails. Everything else passes.

    That failure is the system reporting an unanswered question, not a finding
    of danger, and it clears once tools/fetch_chemistry.py can reach PubChem.
    """
    r = E.run_safety_gates(_assay(), _RX, _PP)
    assert len(r["gates"]) == 17
    assert r["failed"] == ["hazard_resolved"], r["summary"]
    detail = _gate(r, "hazard_resolved")["detail"]
    assert "NOT a finding of safety" in detail


def test_fragmentation_blocks_and_trips_forbidden_products():
    """Partial breakup makes mobile microparticles - worse than leaving the
    fragment intact. It must block, and it must also register as a forbidden
    product rather than only as a rate observation."""
    r = E.run_safety_gates(_assay(fragmentation_fraction=0.15), _RX, _PP)
    assert r["blocking"]
    assert "fragmentation" in r["failed"]
    assert "forbidden_products" in r["failed"]
    assert _gate(r, "fragmentation")["value"] > _gate(r, "fragmentation")["threshold"]


def test_poor_capture_blocks():
    r = E.run_safety_gates(
        _assay(capture_rate_per_h=0.01, capture_capacity_umol=1.0), _RX, _PP)
    assert r["blocking"]
    assert "capture_efficiency" in r["failed"]


def test_negligible_erosion_is_a_no_go_not_a_safe_option():
    r = E.run_safety_gates(_assay(k_cat=1e-6), _RX, _PP)
    assert r["blocking"]
    assert "meaningful_erosion" in r["failed"]


def test_protease_route_is_refused_on_chemistry_alone():
    """A collagenase-style route cannot be made fragment-selective, so it is
    refused regardless of how good its numbers look."""
    r = E.run_safety_gates(_assay(), {**_RX, "bond_class": "peptide bond"}, _PP)
    assert "tissue_off_target" in r["failed"]


def test_high_risk_anatomy_is_routed_out():
    r = E.run_safety_gates(_assay(), _RX, {**_PP, "anatomy_class": "near_nerve"})
    assert "anatomical_tier" in r["failed"]


def test_weak_material_id_blocks_before_any_chemistry_is_credited():
    r = E.run_safety_gates(_assay(), _RX, {**_PP, "confidence": 0.0})
    assert "material_identified" in r["failed"]


def test_broken_mass_balance_invalidates_the_run():
    r = E.run_safety_gates({**_assay(), "mass_balance_residual": 0.3}, _RX, _PP)
    assert "mass_balance" in r["failed"]


def test_every_gate_reports_the_number_that_decided_it():
    r = E.run_safety_gates(_assay(fragmentation_fraction=0.2), _RX, _PP)
    for g in r["gates"]:
        assert g["value"] is not None, g["name"]
        assert g["detail"], g["name"]


def test_non_enzymatic_materials_are_refused_at_the_reaction_stage():
    """f2c's own non-enzymatic list: materials with no hydrolysable or
    chelatable bond an enzyme could reach."""
    for mat in ("glass", "lead", "ceramic", "titanium"):
        out = E.define_reaction(mat)
        assert out["ok"] is False
        assert "no-go" in out["recommendation"]


def test_absent_evidence_is_not_reported_as_impossibility():
    """The distinction f2c draws deliberately and this project keeps:
    polyethylene has no documented route, which is not the same claim as
    "polyethylene cannot be degraded"."""
    out = E.define_reaction("PE")
    assert out["ok"] is False
    assert "absent evidence" in out["recommendation"]
    assert "not proof" in out["recommendation"]


def test_the_three_kinds_of_no_stay_distinct():
    no_route = E.define_reaction("PE")["recommendation"]
    non_enzymatic = E.define_reaction("glass")["recommendation"]
    unidentified = E.define_reaction("something nobody named")["recommendation"]
    assert no_route != non_enzymatic != unidentified
    assert "characterize" in unidentified


def test_unidentified_material_does_not_get_a_guessed_reaction():
    out = E.define_reaction("unknown")
    assert out["ok"] is False
    assert "characterize" in out["recommendation"]


# ---------------------------------------------------------------- provenance
#
# The gates that exist because no turnover number in the knowledge base was
# ever measured on a solid polymer.


@pytest.mark.parametrize("provenance", ["model", "unknown"])
def test_proxy_kinetics_are_refused(provenance):
    """A constant measured on a chromogenic stand-in cannot support a rate."""
    r = E.run_safety_gates(_assay(kinetics_provenance=provenance), _RX, _PP)
    assert r["blocking"]
    assert "kinetics_provenance" in r["failed"]


def test_the_refusal_names_the_actual_assay_substrate():
    """A reviewer must be able to see WHAT it was measured on, not just that
    the gate failed."""
    r = E.run_safety_gates(
        _assay(kinetics_provenance="model", measured_on="4-nitrophenyl butanoate"),
        _RX, _PP)
    gate = _gate(r, "kinetics_provenance")
    assert "4-nitrophenyl butanoate" in gate["detail"]


def test_proxy_provenance_also_widens_the_band_until_confidence_fails():
    """Two independent mechanisms must catch this, not one: the provenance gate
    names it, and the widened band trips the confidence gate on its own."""
    model = _assay(kinetics_provenance="model")
    polymer = _assay(kinetics_provenance="polymer")
    assert model["uncertainty"] > 3 * polymer["uncertainty"]
    r = E.run_safety_gates(model, _RX, _PP)
    assert "predictive_confidence" in r["failed"]


def test_oligomer_evidence_is_allowed_through():
    """A soluble oligomer of the real material is weak evidence, not absent
    evidence - the gate must distinguish the two."""
    r = E.run_safety_gates(_assay(kinetics_provenance="oligomer"), _RX, _PP)
    assert "kinetics_provenance" not in r["failed"]


def test_an_unmeasured_kcat_is_never_silently_defaulted():
    """The failure mode this guards against: a generic fallback producing a
    number indistinguishable from a measured one."""
    base = {k: v for k, v in _BASE.items() if k != "k_cat"}
    a = E.simulate_hydrogel_assay(_CAND, base, {"hours": 336.0},
                                  product="cellobiose", n_samples=24, seed=5)
    assert "k_cat" in a["assumed_parameters"]
    r = E.run_safety_gates(a, _RX, _PP)
    assert "measured_inputs" in r["failed"]


def test_measured_inputs_pass_when_both_constants_are_real():
    a = _assay()
    assert "k_cat" not in a["assumed_parameters"]
    assert "K_m" not in a["assumed_parameters"]
    r = E.run_safety_gates(a, _RX, _PP)
    assert "measured_inputs" not in r["failed"]


# ---------------------------------------------------------------- host safety
#
# The gate that exists because every peptidase in the knowledge base is
# retrieved as a PLA candidate, and a spec-level bond-class check waves them
# through.


def test_a_protease_candidate_is_refused_even_when_the_target_bond_is_not_a_tissue_bond():
    """PLA hydrolysis is aliphatic-ester chemistry, so the reaction-level
    tissue check passes. The enzyme-level check must not."""
    proteinase_k = {"name": "Proteinase K", "ec_numbers": ["3.4.21.64"],
                    "risks": [{"kind": "proteolysis",
                               "host_substrate": "host structural proteins",
                               "why": "broad-spectrum serine endopeptidase",
                               "severity": "blocking", "tier": "established",
                               "basis": "EC 3.4.21"}],
                    "worst_severity": "blocking", "blocking": True}
    r = E.run_safety_gates(_assay(enzyme_safety=proteinase_k), _RX, _PP)
    assert r["blocking"]
    assert "enzyme_host_safety" in r["failed"]
    # and the ester-bond reaction check still passes, proving the two are
    # genuinely independent questions
    assert "tissue_off_target" not in r["failed"]


def test_an_unscreened_enzyme_fails_rather_than_passing_by_default():
    """Not asking is not the same as a negative answer."""
    base = {k: v for k, v in _BASE.items() if k != "enzyme_safety"}
    a = E.simulate_hydrogel_assay(_CAND, base, {"hours": 336.0},
                                  product="cellobiose", n_samples=16, seed=5)
    r = E.run_safety_gates(a, _RX, _PP)
    assert "enzyme_host_safety" in r["failed"]
    detail = _gate(r, "enzyme_host_safety")["detail"]
    assert "not the same as a negative answer" in detail


def test_free_iron_products_block_on_their_mechanism():
    rx = {"bond_class": "metallic Fe(0)", "mechanism": "redox",
          "products": ["fe_ion"], "forbidden_products": ["microparticle"]}
    r = E.run_safety_gates(_assay(), rx, _PP)
    assert "product_hazard" in r["failed"]
    assert "Fenton" in _gate(r, "product_hazard")["detail"]


def test_a_metabolite_only_product_panel_passes_the_hazard_gate():
    rx = {"bond_class": "beta-1,4-glycosidic", "mechanism": "hydrolysis",
          "products": ["cellobiose", "glucose"],
          "forbidden_products": ["microparticle"]}
    r = E.run_safety_gates(_assay(), rx, _PP)
    assert "product_hazard" not in r["failed"]


# ---------------------------------------------------------------- presentation
#
# The two approaches the project can take, and the different questions each has
# to answer.


def test_a_retrievable_single_fragment_is_refused_in_favour_of_surgery():
    """The comparator for this whole approach is forceps, not doing nothing.
    A system that never asks is assuming its own necessity."""
    r = E.run_safety_gates(_assay(), _RX,
                           {**_PP, "retrievable_mechanically": True})
    assert r["blocking"]
    assert "clinical_necessity" in r["failed"]
    detail = _gate(r, "clinical_necessity")["detail"]
    assert "conventional retrieval" in detail


def test_an_unreachable_single_fragment_qualifies():
    r = E.run_safety_gates(_assay(), _RX,
                           {**_PP, "retrievable_mechanically": False})
    assert "clinical_necessity" not in r["failed"]


def test_dispersed_particulate_has_no_conventional_comparator():
    """Thousands of micron-scale particles cannot be picked out at any cost, so
    the necessity question answers itself."""
    a = _assay(presentation="dispersed_particulate", particle_size_um=30.0)
    r = E.run_safety_gates(a, _RX, {**_PP,
                                    "presentation": "dispersed_particulate",
                                    "retrievable_mechanically": False})
    assert "clinical_necessity" not in r["failed"]
    assert "not an option at any cost" in _gate(r, "clinical_necessity")["detail"]


def test_dispersal_raises_surface_area_by_orders_of_magnitude():
    """The reason the dispersed case is tractable at all: same mass, vastly
    more surface."""
    single = _assay()
    dispersed = _assay(presentation="dispersed_particulate", particle_size_um=30.0)
    assert dispersed["n_particles"] > 100_000
    assert dispersed["initial_area_mm2"] > 20 * single["initial_area_mm2"]
    assert dispersed["specific_area_mm2_per_mm3"] > single["specific_area_mm2_per_mm3"]


def test_dispersal_shortens_time_to_half_consumption():
    single = _assay()
    dispersed = _assay(presentation="dispersed_particulate", particle_size_um=30.0)
    assert dispersed["time_to_half_h"] is not None
    assert single["time_to_half_h"] is not None
    assert dispersed["time_to_half_h"] < single["time_to_half_h"]


def test_mass_balance_still_closes_for_a_particle_population():
    """Millions of particles must not break conservation."""
    a = _assay(presentation="dispersed_particulate", particle_size_um=10.0)
    assert a["mass_balance_residual"] < 1e-6
