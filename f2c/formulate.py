"""Layer 5 -- what the hydrogel has to absorb.

Mass balance gives a hard bound with no kinetic assumption at all: whatever the
rate, complete degradation of a fragment of known mass releases a known molar
quantity of monomer. That bound is the capture capacity the carrier must have.

The *rate* is a different question and the public record does not answer it --
no dataset ties a sequence to turnover on a solid fragment in muscle. So this
module reports capacity, and explicitly declines to report a schedule.
"""
from __future__ import annotations

from typing import Any

# Repeat-unit masses, g/mol, from the polymer's defined repeat structure.
# Polymers whose repeat unit is not fixed by the class (PUR, PBAT, rubber)
# are deliberately absent rather than given a representative value.
REPEAT_UNIT_G_PER_MOL: dict[str, float] = {
    "PET": 192.17,   # -OC-C6H4-CO-O-CH2CH2-O-
    "PEF": 182.13,   # furanoate analogue of PET
    "PLA": 72.06,    # lactide residue
    "PHA": 86.09,    # 3-hydroxybutyrate residue
    "PBS": 172.18,   # butylene succinate
    "PC": 254.28,    # bisphenol-A carbonate
    "PA": 113.16,    # caprolactam residue (polyamide 6)
}

# Monomers released on complete hydrolysis, for the ones we bound above.
HYDROLYSIS_PRODUCTS: dict[str, list[str]] = {
    "PET": ["terephthalic acid", "ethylene glycol"],
    "PEF": ["2,5-furandicarboxylic acid", "ethylene glycol"],
    "PLA": ["lactic acid"],
    "PHA": ["3-hydroxybutyric acid"],
    "PBS": ["succinic acid", "1,4-butanediol"],
    "PC": ["bisphenol A", "carbonate"],
    "PA": ["6-aminohexanoic acid"],
}

# Monomers that are ordinary metabolites versus ones needing active capture.
METABOLIC = {"lactic acid", "3-hydroxybutyric acid", "succinic acid"}


def capture_requirement(material_key: str, mass_mg: float | None) -> dict[str, Any]:
    """Bound the product burden from complete degradation of the fragment."""
    repeat = REPEAT_UNIT_G_PER_MOL.get(material_key)
    products = HYDROLYSIS_PRODUCTS.get(material_key, [])

    if repeat is None:
        return {
            "computable": False,
            "reason": (
                f"{material_key} has no fixed repeat-unit mass at the polymer-class "
                "level, so the released molar quantity cannot be bounded from mass "
                "alone. The fragment's own composition has to be characterised first."
            ),
            "products": products,
        }
    if mass_mg is None:
        return {
            "computable": False,
            "reason": "fragment mass not supplied; capture capacity scales linearly with it",
            "products": products,
        }

    # Kept at full precision: rounding here would break the linearity of the
    # mass balance, so formatting is the report's job, not this function's.
    total_mmol = (mass_mg / 1000.0) / repeat * 1000.0
    needs_capture = [p for p in products if p not in METABOLIC]

    return {
        "computable": True,
        "basis": "closed mass balance at complete degradation; no kinetic assumption",
        "repeat_unit_g_per_mol": repeat,
        "total_product_mmol": total_mmol,
        "products": products,
        "requires_active_capture": needs_capture,
        "metabolically_cleared": [p for p in products if p in METABOLIC],
        "capture_capacity_mmol": total_mmol * len(needs_capture) if needs_capture else 0.0,
        "rate": (
            "not reported: turnover of a solid fragment under serum and a protein "
            "corona is not in the public record, so no release schedule is derivable "
            "from these sources"
        ),
    }


# Densities, g/cm3, for converting mass and particle size into surface area.
DENSITY_G_CM3: dict[str, float] = {
    "PET": 1.38, "PEF": 1.43, "PLA": 1.24, "PHA": 1.25,
    "PBS": 1.26, "PC": 1.20, "PA": 1.14, "PBAT": 1.26, "PUR": 1.20, "NR": 0.93,
}

# Above this, the crystalline fraction is the dominant barrier to an enzyme
# reaching the chain. Below it, enough amorphous material is exposed that
# accessibility is not the first thing to fix.
CRYSTALLINITY_BARRIER_PCT = 30.0


def geometry(material_key: str, mass_mg: float | None, particle_size_mm: float | None) -> dict[str, Any]:
    """Specific surface area of the fragment.

    Surface erosion scales with area, not mass, so this is the quantity a rate
    would be expressed per. It is reported as a derived property of the input
    and never turned into a rate, because the turnover figure that would make
    it a rate does not exist for a solid fragment.
    """
    density = DENSITY_G_CM3.get(material_key)
    if density is None or mass_mg is None:
        return {"computable": False,
                "reason": "needs fragment mass and a density for this polymer"}

    volume_cm3 = (mass_mg / 1000.0) / density
    out: dict[str, Any] = {
        "computable": True,
        "density_g_cm3": density,
        "volume_mm3": volume_cm3 * 1000.0,
    }
    if particle_size_mm and particle_size_mm > 0:
        # One cube of the stated edge length, repeated to make up the volume:
        # a defensible first approximation that makes the size input do real work.
        edge_cm = particle_size_mm / 10.0
        per_particle_cm3 = edge_cm ** 3
        count = max(1.0, volume_cm3 / per_particle_cm3)
        area_cm2 = count * 6.0 * edge_cm ** 2
        out.update({
            "particle_size_mm": particle_size_mm,
            "approx_particle_count": round(count, 1),
            "surface_area_mm2": round(area_cm2 * 100.0, 2),
            "specific_area_mm2_per_mg": round(area_cm2 * 100.0 / mass_mg, 3),
            "basis": "cubes of the stated edge length filling the fragment volume",
        })
    else:
        out["note"] = "particle size not characterised; surface area cannot be bounded"
    return out


def accessibility_gaps(
    material_key: str,
    crystallinity_pct: float | None,
    protein_corona: bool,
    catalytic_class: str | None = None,
) -> list[dict[str, Any]]:
    """Barriers between the enzyme and the chain it has to cut.

    These belong to the fragment rather than the enzyme, so they are reported
    separately: swapping the catalyst does not remove them.
    """
    out: list[dict[str, Any]] = []

    if crystallinity_pct is None:
        out.append({
            "kind": "crystallinity",
            "detail": "crystallinity not characterised",
            "severity": "unknown",
            "action": "measure it; it decides whether the enzyme can reach the chain at all",
        })
    elif crystallinity_pct >= CRYSTALLINITY_BARRIER_PCT:
        severity = "high" if crystallinity_pct >= 45 else "moderate"
        detail = (
            f"{crystallinity_pct:g}% crystalline. Enzymes act on amorphous regions; "
            "the crystalline fraction resists attack and sets the ceiling on how much "
            "of this fragment can be degraded at all"
        )
        if catalytic_class and catalytic_class != "polymer":
            detail += (
                ". The selected enzyme's constants come from soluble substrates, "
                "where crystallinity does not apply, so they say nothing about this barrier"
            )
        out.append({
            "kind": "crystallinity", "detail": detail, "severity": severity,
            "action": "assay on material of the same crystallinity as the fragment, "
                      "or pre-treat to reduce it",
        })

    if protein_corona:
        out.append({
            "kind": "surface state",
            "detail": "a fragment in tissue carries adsorbed plasma protein and, in "
                      "trauma, soil and blood. The enzyme meets that layer, not the polymer",
            "severity": "moderate",
            "action": "include the corona in the assay rather than using clean coupons",
        })
    return out


def residue_note(material_key: str) -> str:
    """What is left once the polymer phase is gone."""
    return (
        "Inorganic inclusions and surface contamination are not enzyme substrates and "
        "persist after the polymer phase is consumed. Their fate is governed by "
        "particle size rather than chemistry, which makes residue size a measured "
        "endpoint of any degradation experiment, not an afterthought."
    )
