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


def residue_note(material_key: str) -> str:
    """What is left once the polymer phase is gone."""
    return (
        "Inorganic inclusions and surface contamination are not enzyme substrates and "
        "persist after the polymer phase is consumed. Their fate is governed by "
        "particle size rather than chemistry, which makes residue size a measured "
        "endpoint of any degradation experiment, not an afterthought."
    )
