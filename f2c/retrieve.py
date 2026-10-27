"""Layer 2a -- material in, candidate catalysts out.

Two kinds of "no" are possible and they are not the same thing:

* the material has no hydrolysable or otherwise enzyme-accessible bond at all
  (glass, metal, a pure C-C backbone), which is a statement about chemistry;
* the material is in principle degradable but the seed set holds no enzyme
  whose activity on it was ever demonstrated, which is a statement about the
  evidence we have.

Collapsing them would let the second quietly masquerade as the first.
"""
from __future__ import annotations

from dataclasses import dataclass

from .schema import MaterialSpec, Protein

# Materials outside the enzymatic-degradation domain, with the mechanistic
# reason. An enzyme hydrolyses or redox-cycles a specific bond; none of these
# presents one that a secreted protein can turn over at body conditions.
NON_ENZYMATIC: dict[str, str] = {
    "glass": "Si-O-Si network; no hydrolysable bond accessible to a secreted enzyme at 37 C",
    "silica": "Si-O-Si network; no hydrolysable bond accessible to a secreted enzyme at 37 C",
    "ceramic": "ionic/covalent refractory lattice; no enzyme substrate",
    "stone": "mineral lattice; no enzyme substrate",
    "steel": "metallic lattice; degradation would be redox corrosion, not hydrolysis",
    "iron": "metallic lattice; degradation would be redox corrosion, not hydrolysis",
    "lead": "metallic lattice; solubilising it would convert a local deposit into systemic exposure",
    "aluminium": "metallic lattice; degradation would be redox corrosion, not hydrolysis",
    "titanium": "passivated metallic lattice; no enzyme substrate",
}

# Common names mapped onto PAZy's substrate vocabulary.
ALIASES: dict[str, str] = {
    "pet": "PET",
    "polyester": "PET",
    "polyethylene terephthalate": "PET",
    "pur": "PUR",
    "polyurethane": "PUR",
    "pla": "PLA",
    "polylactic acid": "PLA",
    "pa": "PA",
    "polyamide": "PA",
    "nylon": "PA",
    "pbat": "PBAT",
    "pbs": "PBS",
    "pc": "PC",
    "polycarbonate": "PC",
    "pef": "PEF",
    "pha": "PHA",
    "nr": "NR",
    "natural rubber": "NR",
    "pe": "PE",
    "polyethylene": "PE",
    "pp": "PP",
    "polypropylene": "PP",
    "ps": "PS",
    "polystyrene": "PS",
    "pvc": "PVC",
}


@dataclass
class Retrieval:
    material_key: str | None
    candidates: list[Protein]
    blocked_reason: str | None = None
    oligomer_only_excluded: int = 0


def normalise(polymer: str) -> str:
    return ALIASES.get(polymer.strip().lower(), polymer.strip().upper())


def retrieve(material: MaterialSpec, proteins: list[Protein]) -> Retrieval:
    raw = material.polymer.strip().lower()
    if raw in NON_ENZYMATIC:
        return Retrieval(
            material_key=None,
            candidates=[],
            blocked_reason=(
                f"{material.polymer}: {NON_ENZYMATIC[raw]}. "
                "No enzymatic degradation route exists; this fragment belongs to the "
                "capsule-modulation arm, not the catalyst arm."
            ),
        )

    key = normalise(material.polymer)
    candidates: list[Protein] = []
    excluded = 0

    for protein in proteins:
        for sub in protein.substrates:
            if (sub.get("abbreviation") or "").upper() != key:
                continue
            # Activity shown only on soluble oligomers does not demonstrate the
            # enzyme can erode a solid polymer fragment.
            if sub.get("oligomer_only") and material.is_polymeric():
                excluded += 1
                break
            candidates.append(protein)
            break

    return Retrieval(
        material_key=key, candidates=candidates, oligomer_only_excluded=excluded
    )
