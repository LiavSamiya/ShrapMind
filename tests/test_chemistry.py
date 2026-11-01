"""The compound layer: identity in, physics derived, hazard never invented."""
import pytest

from f2c.sources import chemistry as C


def test_molecular_weight_is_computed_not_recalled():
    """Weights come from the formula and a periodic table, so they can be
    checked by hand rather than taken on trust."""
    for formula, expected in (("H2O", 18.015), ("C6H12O6", 180.156),
                              ("C8H6O4", 166.132), ("C2H6O2", 62.068),
                              ("C15H16O2", 228.291)):
        assert C.molecular_weight(formula) == pytest.approx(expected, abs=0.01)


@pytest.mark.parametrize("bad", ["", "C6(H12)O6", "Xx9", "C6H12O6junk", "6H12O"])
def test_malformed_formulas_are_rejected_not_guessed(bad):
    with pytest.raises(C.FormulaError):
        C.molecular_weight(bad)


def test_radius_rises_with_molecular_size():
    r = [C.radius_nm_from_mw(C.molecular_weight(f))
         for f in ("C2H6O2", "C6H12O6", "C12H22O11")]
    assert r == sorted(r)


def test_radius_matches_the_literature_scale_for_glucose():
    """The sanity check that justifies using this correlation at all:
    reported Stokes radii for glucose cluster around 0.36-0.44 nm."""
    r = C.radius_nm_from_mw(C.molecular_weight("C6H12O6"))
    assert 0.34 <= r <= 0.46


def test_the_correlation_refuses_to_extrapolate_below_its_range():
    """It is fitted to solutes of roughly 50 g/mol and up. Returning a
    confident number for water would be exactly the false precision this
    project exists to avoid."""
    with pytest.raises(C.FormulaError):
        C.radius_nm_from_mw(18.0)


def test_ions_use_an_ionic_radius_not_the_organic_correlation():
    store = C.load()
    fe = store["fe_ion"]
    assert fe.radius_nm == C.IONIC_RADIUS_NM["fe_ion"]
    assert fe.level == "reference"
    assert "ionic radius" in fe.notes


def test_hazard_is_never_populated_offline():
    """GHS codes are regulatory strings. A gate firing on a half-remembered
    hazard code would be worse than a gate with no data, so the snapshot ships
    with hazard unresolved and the gate reports it as a question."""
    for key, c in C.load().items():
        assert c.ghs_codes is None, f"{key} has hand-entered hazard data"
        assert not c.hazard_resolved


def test_every_reaction_product_is_characterised():
    """Every product any material route can release must have identity in the
    store, because its radius drives the capture gate."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client" / "worker"))
    import engines as E

    store = C.load()
    missing = []
    for name, spec in E.MATERIALS.items():
        for prod in spec["products"]:
            if prod not in store:
                missing.append(f"{name}:{prod}")
    assert missing == [], f"products with no compound record: {missing}"


def test_derived_values_are_labelled_as_derived():
    store = C.load()
    assert store["ethylene_glycol"].level == "derived"
    assert store["ethylene_glycol"].molecular_weight is not None
    # and a value with no formula is not silently promoted
    assert store["microparticle"].level == "reference"


def test_snapshot_round_trips(tmp_path):
    path = tmp_path / "compounds.json"
    C.save(C.reference_set(), path)
    back = C.load(path)
    ref = C.reference_set()
    assert set(back) == set(ref)
    assert back["mhet"].molecular_weight == ref["mhet"].molecular_weight
