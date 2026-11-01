"""The surface-erosion model.

WHAT THIS IS
    A parametric, lumped-compartment kinetic model of enzymatic surface
    erosion of a solid fragment held inside a hydrogel. It integrates four
    coupled pools over time and closes mass balance:

        fragment  ->  free products  ->  gel-captured  ->  cleared

    Rates come from literature/BRENDA-style kinetic records held in the
    database (k_cat, K_m, temperature and pH optima), modulated by
    diffusion through the gel mesh and by physiological conditions.

WHAT THIS IS NOT
    Not molecular dynamics. Not a docking or structure-prediction engine. It
    cannot tell you whether a designed sequence folds, expresses or binds -
    it tells you what erosion rate a given set of measured kinetic parameters
    implies under a given set of conditions, with an uncertainty band.

    Its value is ranking and triage: narrowing thousands of candidate
    families to the handful worth a wet-lab experiment, and refusing the ones
    that fail a safety gate. Every number it emits is a hypothesis.

WHY SURFACE EROSION AND NOT BULK DEGRADATION
    A solid fragment is attacked only where enzyme can reach it. The rate is
    therefore proportional to accessible surface area, which shrinks as the
    fragment shrinks. That matters clinically as well as numerically: surface
    erosion keeps the object intact and shrinking, whereas bulk scission
    would fragment it into mobile particles - the failure mode the safety
    gates exist to catch.

NUMERICS
    Fixed-step explicit integration (RK4) with a step-size guard. numpy only;
    no scipy dependency. Deterministic for a given seed so the mock demo and
    the tests reproduce exactly.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

try:
    import numpy as np
except ImportError:  # pragma: no cover - worker requirements install numpy
    np = None  # type: ignore[assignment]

# Gas constant / reference temperature for the Arrhenius-style factor.
_R = 8.314462618  # J/(mol*K)
_T_REF = 310.15  # 37 degC in K

# Molecular radius (nm) per product, for the mesh-hindrance term.
#
# These used to be nine hand-written guesses. They now come from the compound
# store, where each radius is either derived from the compound's molecular
# weight (itself computed from its formula) or, for ions, an ionic radius -
# with the provenance recorded per value. See f2c/sources/chemistry.py.
#
# This matters more than it looks: the radius feeds mesh_hindrance(), which
# sets how much product escapes the gel, which is what the capture gate
# measures. Guessed radii meant a guessed safety verdict.
_FALLBACK_RADIUS_NM = 1.0


def _product_radii() -> dict[str, float]:
    try:
        from f2c.sources.chemistry import load

        return {k: c.radius_nm for k, c in load().items() if c.radius_nm}
    except Exception:  # noqa: BLE001 - the simulator must still run standalone
        return {}


try:
    _PRODUCT_RADIUS_NM: dict[str, float] = _product_radii()
except Exception:  # noqa: BLE001
    _PRODUCT_RADIUS_NM = {}


@dataclass
class EnzymeParams:
    """Kinetic record for one candidate, as held in `enzyme_families`."""

    name: str = "unknown"
    k_cat: float = 1.0            # 1/s, turnover on the solid substrate
    k_m_uM: float = 50.0          # uM, apparent K_m
    t_opt_c: float = 37.0         # degC
    t_width_c: float = 12.0       # degC, tolerance half-width
    ph_opt: float = 7.0
    ph_width: float = 1.2
    ea_kj: float = 45.0           # kJ/mol, apparent activation energy
    radius_nm: float = 3.0        # hydrodynamic radius of the enzyme
    half_life_h: float = 72.0     # inactivation half-life at 37 degC
    product: str = "oligomer"
    # Fraction of turnover that detaches a particle rather than a soluble
    # product. This is the single most safety-relevant parameter in the model.
    fragmentation_fraction: float = 0.0


@dataclass
class GelParams:
    """The hydrogel environment the fragment and enzyme sit in."""

    mesh_nm: float = 20.0
    volume_ul: float = 500.0
    # Fraction of released product the gel captures per unit time constant.
    capture_rate_per_h: float = 0.35
    capture_capacity_umol: float = 50.0
    clearance_rate_per_h: float = 0.02  # lymphatic/vascular removal from gel


@dataclass
class FragmentParams:
    """Geometry of the solid. Sphere-equivalent shrinking-core."""

    volume_mm3: float = 10.0
    density_g_cm3: float = 1.4
    molar_mass_g_mol: float = 162.14  # cellulose monomer by default
    # Fraction of the surface that is chemically accessible (coating,
    # crystallinity and protein fouling all reduce this).
    accessibility: float = 0.6


@dataclass
class Conditions:
    temperature_c: float = 37.0
    ph: float = 7.4
    enzyme_uM: float = 10.0
    serum_fraction: float = 0.1
    hours: float = 168.0
    timestep_h: float = 0.5


@dataclass
class Trace:
    """Integration output. All pools in umol except radius/area."""

    t_h: list[float] = field(default_factory=list)
    fragment_umol: list[float] = field(default_factory=list)
    free_umol: list[float] = field(default_factory=list)
    captured_umol: list[float] = field(default_factory=list)
    cleared_umol: list[float] = field(default_factory=list)
    particles_umol: list[float] = field(default_factory=list)
    radius_mm: list[float] = field(default_factory=list)
    area_mm2: list[float] = field(default_factory=list)


def _sphere_radius_mm(volume_mm3: float) -> float:
    return (3.0 * max(volume_mm3, 0.0) / (4.0 * math.pi)) ** (1.0 / 3.0)


def _sphere_area_mm2(radius_mm: float) -> float:
    return 4.0 * math.pi * radius_mm * radius_mm


def temperature_factor(p: EnzymeParams, t_c: float) -> float:
    """Arrhenius rise multiplied by a Gaussian denaturation envelope.

    Pure Arrhenius would predict that hotter is always faster, which is wrong
    for a protein; the envelope encodes the optimum and the fall-off past it.
    """
    t_k = t_c + 273.15
    arr = math.exp(-(p.ea_kj * 1000.0 / _R) * (1.0 / t_k - 1.0 / _T_REF))
    env = math.exp(-0.5 * ((t_c - p.t_opt_c) / max(p.t_width_c, 1e-6)) ** 2)
    return max(arr * env, 0.0)


def ph_factor(p: EnzymeParams, ph: float) -> float:
    return math.exp(-0.5 * ((ph - p.ph_opt) / max(p.ph_width, 1e-6)) ** 2)


def mesh_hindrance(radius_nm: float, mesh_nm: float) -> float:
    """Ogston-style hindered-diffusion factor for a sphere in a mesh.

    Returns ~1 when the molecule is far smaller than the mesh and ->0 as it
    approaches the mesh size. This is what makes the gel a selective filter:
    small products diffuse out, microparticles do not.
    """
    if mesh_nm <= 0:
        return 0.0
    ratio = radius_nm / mesh_nm
    if ratio >= 1.0:
        return 0.0
    return float(math.exp(-2.0 * ratio) * (1.0 - ratio) ** 2)


def serum_factor(serum_fraction: float) -> float:
    """Protein fouling: serum proteins adsorb and block the surface."""
    return 1.0 / (1.0 + 2.5 * max(serum_fraction, 0.0))


def effective_rate_constant(
    enzyme: EnzymeParams, gel: GelParams, cond: Conditions
) -> float:
    """Surface-specific turnover, umol per mm2 per hour.

    Michaelis-Menten in the enzyme concentration, scaled by the condition
    factors and by how well the enzyme itself can move through the mesh.
    """
    mm = cond.enzyme_uM / (enzyme.k_m_uM + cond.enzyme_uM)
    f_t = temperature_factor(enzyme, cond.temperature_c)
    f_ph = ph_factor(enzyme, cond.ph)
    f_mesh = mesh_hindrance(enzyme.radius_nm, gel.mesh_nm)
    f_serum = serum_factor(cond.serum_fraction)
    # k_cat (1/s) -> per hour, times a surface-site density proxy (umol/mm2).
    site_density_umol_mm2 = 2.0e-4
    return enzyme.k_cat * 3600.0 * site_density_umol_mm2 * mm * f_t * f_ph * f_mesh * f_serum


def simulate(
    enzyme: EnzymeParams,
    gel: GelParams,
    fragment: FragmentParams,
    cond: Conditions,
) -> dict[str, Any]:
    """Integrate the four-pool model. Returns a trace plus summary metrics.

    Mass balance closes by construction: every umol leaving the fragment pool
    enters exactly one of free / captured / cleared / particles. The residual
    is reported anyway, because a residual that is not ~0 means the
    integration is unstable and the result must not be trusted - and
    `run_safety_gates` treats that as a failure.
    """
    # Total substrate in the fragment, umol.
    mass_g = fragment.volume_mm3 * 1e-3 * fragment.density_g_cm3
    total_umol = mass_g / fragment.molar_mass_g_mol * 1e6
    if total_umol <= 0:
        raise ValueError("fragment has zero substrate mass")

    k_surf = effective_rate_constant(enzyme, gel, cond)
    r0 = _sphere_radius_mm(fragment.volume_mm3)
    k_inact = math.log(2.0) / max(enzyme.half_life_h, 1e-6)
    prod_radius = _PRODUCT_RADIUS_NM.get(enzyme.product, _FALLBACK_RADIUS_NM)
    radius_known = enzyme.product in _PRODUCT_RADIUS_NM
    escape = mesh_hindrance(prod_radius, gel.mesh_nm)

    # State: fragment, free, captured, cleared, particles (umol)
    y = [total_umol, 0.0, 0.0, 0.0, 0.0]
    dt = max(min(cond.timestep_h, 6.0), 1e-3)
    n = max(int(cond.hours / dt), 1)
    tr = Trace()

    def deriv(t: float, s: list[float]) -> list[float]:
        frag, free, capt, clr, part = s
        frag = max(frag, 0.0)
        # Shrinking-core: current radius from remaining fraction.
        frac = frag / total_umol
        radius = r0 * (frac ** (1.0 / 3.0)) if frac > 0 else 0.0
        area = _sphere_area_mm2(radius) * fragment.accessibility
        activity = math.exp(-k_inact * t)
        release = k_surf * area * activity  # umol/h off the surface
        release = min(release, frag / dt if dt > 0 else release)
        to_particles = release * enzyme.fragmentation_fraction
        to_free = release - to_particles
        # Capture saturates at the gel's binding capacity.
        head = max(1.0 - capt / max(gel.capture_capacity_umol, 1e-9), 0.0)
        capture = gel.capture_rate_per_h * free * head * (1.0 - escape)
        clearance = gel.clearance_rate_per_h * free * escape
        return [
            -release,
            to_free - capture - clearance,
            capture,
            clearance,
            to_particles,
        ]

    t = 0.0
    for i in range(n + 1):
        frac = max(y[0], 0.0) / total_umol
        radius = r0 * (frac ** (1.0 / 3.0)) if frac > 0 else 0.0
        tr.t_h.append(round(t, 4))
        tr.fragment_umol.append(y[0])
        tr.free_umol.append(y[1])
        tr.captured_umol.append(y[2])
        tr.cleared_umol.append(y[3])
        tr.particles_umol.append(y[4])
        tr.radius_mm.append(radius)
        tr.area_mm2.append(_sphere_area_mm2(radius) * fragment.accessibility)
        if i == n:
            break
        # RK4
        k1 = deriv(t, y)
        k2 = deriv(t + dt / 2, [y[j] + dt / 2 * k1[j] for j in range(5)])
        k3 = deriv(t + dt / 2, [y[j] + dt / 2 * k2[j] for j in range(5)])
        k4 = deriv(t + dt, [y[j] + dt * k3[j] for j in range(5)])
        y = [y[j] + dt / 6 * (k1[j] + 2 * k2[j] + 2 * k3[j] + k4[j]) for j in range(5)]
        y[0] = max(y[0], 0.0)
        y = [max(v, 0.0) for v in y]
        t += dt

    consumed = total_umol - y[0]
    residual = abs(total_umol - sum(y)) / total_umol

    # Surface erosion rate in um/day - the number a reviewer actually reads.
    #
    # Measured over the window in which erosion is actually happening, not
    # over the whole requested horizon. Otherwise a fragment that is fully
    # consumed on day 3 of a 90-day run reports a rate 30x too low, and two
    # very different candidates both report "fully consumed" at the same
    # apparent rate. We stop the clock when the fragment is gone.
    depleted_at_h = cond.hours
    for idx, frag in enumerate(tr.fragment_umol):
        if frag <= total_umol * 1e-4:
            depleted_at_h = tr.t_h[idx]
            break
    dr_mm = max(r0 - tr.radius_mm[-1], 0.0)
    days = max(depleted_at_h / 24.0, 1e-9)
    erosion_um_day = dr_mm * 1000.0 / days
    time_to_half_h = None
    for idx, frag in enumerate(tr.fragment_umol):
        if frag <= total_umol * 0.5:
            time_to_half_h = tr.t_h[idx]
            break

    return {
        "trace": asdict(tr),
        "total_umol": total_umol,
        "consumed_umol": consumed,
        "consumed_fraction": consumed / total_umol,
        "mass_balance_residual": residual,
        "erosion_rate_um_per_day": erosion_um_day,
        "depleted_at_h": depleted_at_h,
        "time_to_half_h": time_to_half_h,
        "radius_start_mm": r0,
        "radius_end_mm": tr.radius_mm[-1],
        "free_end_umol": y[1],
        "captured_end_umol": y[2],
        "cleared_end_umol": y[3],
        "particles_end_umol": y[4],
        "captured_fraction": (y[2] / consumed) if consumed > 1e-12 else 0.0,
        "free_fraction": (y[1] / consumed) if consumed > 1e-12 else 0.0,
        "particle_fraction": (y[4] / consumed) if consumed > 1e-12 else 0.0,
        "k_surface_umol_mm2_h": k_surf,
        "product": enzyme.product,
        "product_radius_nm": prod_radius,
        "product_radius_known": radius_known,
    }


def _jitter(value: float, rel: float, rng: Any) -> float:
    """Log-normal jitter so a parameter never goes negative."""
    if value <= 0:
        return value
    return float(value * math.exp(rng.normal(0.0, rel)))


# How wide to make the band, given what the kinetic constants were measured on.
#
# This is the single most important table in the simulator. Nobody has measured
# a turnover number on a solid retained fragment, so every k_cat available is a
# constant measured on something else: a chromogenic ester, a soluble oligomer,
# in the worst case an unrelated protein substrate. Reporting a tight band from
# such a constant would be false precision of the most persuasive kind.
#
# So the provenance sets the spread, and a model-ester-derived rate comes back
# with a band spanning roughly an order of magnitude - which then trips the
# predictive_confidence gate on its own, without needing a special case.
PROVENANCE_SIGMA = {
    "polymer": 0.25,
    "oligomer": 0.50,
    "model": 0.90,
    "unknown": 1.20,
}


def sigma_for(provenance: str | None) -> float:
    return PROVENANCE_SIGMA.get(str(provenance or "unknown"), 1.20)


def simulate_with_uncertainty(
    enzyme: EnzymeParams,
    gel: GelParams,
    fragment: FragmentParams,
    cond: Conditions,
    *,
    n_samples: int = 64,
    seed: int = 0,
    rel_sigma: float | None = None,
    provenance: str | None = None,
) -> dict[str, Any]:
    """Run the model over sampled kinetic parameters and return a band.

    Literature kinetic constants carry real spread - often an order of
    magnitude between papers for the same enzyme. Reporting a single number
    from a single k_cat would be false precision. The band is also what makes
    `plan_next_experiment` possible: the candidate whose predicted rate has
    the widest band is the one a wet-lab measurement would inform most.

    Deterministic for a given seed.
    """
    if np is None:
        raise RuntimeError("numpy is required for simulate_with_uncertainty")
    # Provenance decides the spread unless a caller overrides it explicitly.
    if rel_sigma is None:
        rel_sigma = sigma_for(provenance)
    n = int(max(1, min(n_samples, 512)))
    rng = np.random.default_rng(seed)
    base = simulate(enzyme, gel, fragment, cond)

    rates: list[float] = []
    fracs: list[float] = []
    parts: list[float] = []
    caps: list[float] = []
    for _ in range(n):
        e = EnzymeParams(**{**asdict(enzyme)})
        e.k_cat = _jitter(enzyme.k_cat, rel_sigma, rng)
        e.k_m_uM = _jitter(enzyme.k_m_uM, rel_sigma, rng)
        e.half_life_h = _jitter(enzyme.half_life_h, rel_sigma * 0.8, rng)
        e.t_opt_c = enzyme.t_opt_c + float(rng.normal(0.0, 1.5))
        e.ph_opt = enzyme.ph_opt + float(rng.normal(0.0, 0.15))
        g = GelParams(**asdict(gel))
        g.mesh_nm = _jitter(gel.mesh_nm, rel_sigma * 0.5, rng)
        try:
            r = simulate(e, g, fragment, cond)
        except (ValueError, ZeroDivisionError):
            continue
        rates.append(r["erosion_rate_um_per_day"])
        fracs.append(r["consumed_fraction"])
        parts.append(r["particle_fraction"])
        caps.append(r["captured_fraction"])

    if not rates:
        raise RuntimeError("every uncertainty sample failed to integrate")

    arr = np.array(rates, dtype=float)
    lo, hi = (float(np.percentile(arr, 5)), float(np.percentile(arr, 95)))
    median = float(np.median(arr))
    spread = (hi - lo) / median if median > 0 else float("inf")

    base["erosion_rate_um_per_day"] = median
    base["erosion_rate_ci"] = (lo, hi)
    base["erosion_rate_point"] = base.get("erosion_rate_um_per_day")
    base["n_samples"] = len(rates)
    # Relative width of the band: the active-learning signal.
    base["uncertainty"] = spread
    base["consumed_fraction_ci"] = (
        float(np.percentile(np.array(fracs), 5)),
        float(np.percentile(np.array(fracs), 95)),
    )
    base["particle_fraction_p95"] = float(np.percentile(np.array(parts), 95))
    base["captured_fraction_p05"] = float(np.percentile(np.array(caps), 5))
    base["kinetics_provenance"] = str(provenance or "unknown")
    base["rel_sigma"] = rel_sigma
    return base
