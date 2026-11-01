"""The gate battery. Each gate must fire on the condition it exists for."""
import engines as E
import pytest

_RX = {"bond_class": "beta-1,4-glycosidic", "mechanism": "hydrolysis",
       "products": ["cellobiose"], "forbidden_products": ["microparticle", "formaldehyde"]}
_PP = {"material_family": "cellulose", "anatomy_class": "soft_tissue", "confidence": 0.8}
# A "sound run" fixture now has to state what its kinetics were measured on.
# Provenance "polymer" is the hypothetical case the knowledge base does not yet
# contain anywhere - which is exactly why the gate exists.
_BASE = {"k_cat": 3.0, "k_m_uM": 45.0, "half_life_h": 96.0, "volume_mm3": 8.0,
         "accessibility": 0.3, "mesh_nm": 20.0, "capture_rate_per_h": 0.6,
         "capture_capacity_umol": 200.0, "molar_mass_g_mol": 162.14,
         "density_g_cm3": 1.5, "kinetics_provenance": "polymer",
         "measured_on": "amorphous PET film"}
_CAND = {"name": "cellulase-WT", "parent_family": "cellulase", "edits": []}


def _assay(**base_over):
    return E.simulate_hydrogel_assay(_CAND, {**_BASE, **base_over},
                                     {"hours": 336.0}, product="cellobiose",
                                     n_samples=32, seed=5)


def _gate(result, name):
    return next(g for g in result["gates"] if g["name"] == name)


def test_a_sound_run_passes_every_gate():
    r = E.run_safety_gates(_assay(), _RX, _PP)
    assert r["passed"], r["summary"]
    assert not r["blocking"]
    assert len(r["gates"]) == 12


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


def test_no_go_material_is_refused_at_the_reaction_stage():
    for mat in ("polyethylene", "glass", "lead"):
        out = E.define_reaction(mat)
        assert out["ok"] is False
        assert "no-go" in out["recommendation"]


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
