"""The model must conserve mass. Everything else it says depends on it."""

import kinetics as K
import pytest


def _params(**kw):
    e = K.EnzymeParams(name="t", k_cat=3.0, k_m_uM=45.0, product="cellobiose",
                       half_life_h=96.0)
    for k, v in kw.items():
        setattr(e, k, v)
    return e


def test_mass_balance_closes_across_a_parameter_sweep():
    """Residual must stay at numerical-noise level over the whole legal range."""
    worst = 0.0
    for k_cat in (0.05, 1.0, 20.0):
        for mesh in (5.0, 20.0, 120.0):
            for temp in (20.0, 37.0, 44.0):
                for hours in (24.0, 336.0, 2000.0):
                    r = K.simulate(
                        _params(k_cat=k_cat),
                        K.GelParams(mesh_nm=mesh),
                        K.FragmentParams(volume_mm3=8.0),
                        K.Conditions(temperature_c=temp, hours=hours))
                    worst = max(worst, r["mass_balance_residual"])
    assert worst < 1e-6, f"worst residual {worst:.2e}"


def test_pools_never_go_negative():
    r = K.simulate(_params(k_cat=50.0), K.GelParams(), K.FragmentParams(volume_mm3=0.5),
                   K.Conditions(hours=2000.0))
    tr = r["trace"]
    for key in ("fragment_umol", "free_umol", "captured_umol", "cleared_umol",
                "particles_umol"):
        assert min(tr[key]) >= 0.0, key


def test_erosion_rate_is_independent_of_the_requested_horizon():
    """A fragment consumed on day 4 must not report a slower rate just because
    the caller asked for a 90-day window."""
    a = K.simulate(_params(), K.GelParams(), K.FragmentParams(volume_mm3=8.0),
                   K.Conditions(hours=336.0))
    b = K.simulate(_params(), K.GelParams(), K.FragmentParams(volume_mm3=8.0),
                   K.Conditions(hours=2000.0))
    assert a["erosion_rate_um_per_day"] == pytest.approx(
        b["erosion_rate_um_per_day"], rel=0.02)


def test_mesh_hindrance_discriminates_a_bulky_enzyme():
    """A tight mesh must throttle a large enzyme. If it did not, the gel would
    be doing nothing in the model."""
    small = K.simulate(_params(radius_nm=2.0), K.GelParams(mesh_nm=8.0),
                       K.FragmentParams(), K.Conditions(hours=336.0))
    big = K.simulate(_params(radius_nm=7.0), K.GelParams(mesh_nm=8.0),
                     K.FragmentParams(), K.Conditions(hours=336.0))
    assert big["erosion_rate_um_per_day"] < small["erosion_rate_um_per_day"] / 10


def test_uncertainty_band_brackets_the_median_and_is_deterministic():
    kw = dict(n_samples=48, seed=11)
    a = K.simulate_with_uncertainty(_params(), K.GelParams(), K.FragmentParams(),
                                    K.Conditions(hours=336.0), **kw)
    b = K.simulate_with_uncertainty(_params(), K.GelParams(), K.FragmentParams(),
                                    K.Conditions(hours=336.0), **kw)
    lo, hi = a["erosion_rate_ci"]
    assert lo <= a["erosion_rate_um_per_day"] <= hi
    assert a["erosion_rate_um_per_day"] == b["erosion_rate_um_per_day"]
    assert a["uncertainty"] >= 0.0


def test_zero_mass_fragment_is_refused():
    with pytest.raises(ValueError):
        K.simulate(_params(), K.GelParams(), K.FragmentParams(volume_mm3=0.0),
                   K.Conditions())


def test_uncertainty_is_never_infinite_because_infinity_is_not_valid_json():
    """A zero median rate makes the relative band width undefined. Reporting
    float('inf') would serialise to the token `Infinity`, which JSON.parse
    rejects - so a legitimate "this rate is unmeasurable" finding would reach
    the console as an opaque parse error instead."""
    import json

    r = K.simulate_with_uncertainty(
        _params(k_cat=1e-30), K.GelParams(mesh_nm=2.0),
        K.FragmentParams(volume_mm3=50.0), K.Conditions(hours=24.0),
        n_samples=16, seed=3, provenance="unknown")
    assert r["uncertainty"] <= K._UNCERTAINTY_CAP
    blob = json.dumps(r)
    assert "Infinity" not in blob and "NaN" not in blob
    json.loads(blob)


def test_provenance_sets_the_band_width():
    """polymer < oligomer < model < unknown, monotonically."""
    widths = []
    for prov in ("polymer", "oligomer", "model", "unknown"):
        r = K.simulate_with_uncertainty(
            _params(), K.GelParams(), K.FragmentParams(volume_mm3=8.0),
            K.Conditions(hours=336.0), n_samples=96, seed=11, provenance=prov)
        widths.append(r["uncertainty"])
    assert widths == sorted(widths), widths
