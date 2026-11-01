"""The stages downstream of catalyst selection.

Catalyst selection rests on measurements: PAZy demonstrated activity, UniProt
annotation, BRENDA constants with their assay conditions. Everything after it
— the cocktail, the carrier, the immune response, where the residue ends up —
does not. It is a design specification plus a reading of the literature.

Presenting both at the same visual authority would be the most damaging thing
this interface could do, so every stage carries an explicit `evidence` class:

    measured   a value from the warehouse, with its PMID
    derived    computed from measured values (mass balance)
    specified  a design decision; no measurement backs the number
    literature a published finding, cited, that motivates the decision

Citations here were resolved against PubMed before being written down, and two
of them do not say what the concept brief assumed — see `CAVEATS`.
"""
from __future__ import annotations

from typing import Any

MEASURED, DERIVED, SPECIFIED, LITERATURE = "measured", "derived", "specified", "literature"


def _ref(pmid: str, doi: str, title: str, year: int, says: str) -> dict[str, str]:
    """A citation plus what it actually demonstrates, in its own terms."""
    return {"pmid": pmid, "doi": doi, "title": title, "year": year, "says": says}


# Resolved against PubMed. `says` is what the paper shows, not what we want it
# to show -- the gap between those two is where overclaiming starts.
REFS = {
    "fbr_geometry": _ref(
        "25985456", "10.1038/nmat4290",
        "Size- and shape-dependent foreign body immune response to materials "
        "implanted in rodents and non-human primates",
        2015,
        "Implanted spheres 1.5 mm and above reduced fibrosis relative to smaller "
        "ones, across hydrogels, ceramics, metals and plastics. The variable "
        "tested was geometry, not stiffness.",
    ),
    "silica_lysosome": _ref(
        "18604214", "10.1038/ni.1631",
        "Silica crystals and aluminum salts activate the NALP3 inflammasome "
        "through phagosomal destabilization",
        2008,
        "Phagocytosed silica ruptures the lysosome and activates NALP3. This is "
        "the mechanism that makes undegraded mineral residue inflammatory, and "
        "the reason to coat it.",
    ),
    "tattoo_macrophage": _ref(
        "29511065", "10.1084/jem.20171608",
        "Unveiling skin macrophage dynamics explains both tattoo persistence "
        "and strenuous removal",
        2018,
        "Tattoo pigment is held by dermal macrophages through repeated "
        "capture-release-recapture; persistence rests on macrophage renewal. "
        "The paper does not demonstrate clearance to lymph nodes.",
    ),
}

# Where the concept brief and the cited papers part company. Named here so the
# interface can show it rather than let a reviewer find it.
CAVEATS = [
    {
        "claim": "A soft hydrogel prevents the fibrotic capsule because macrophages "
                 "sense stiffness.",
        "evidence": REFS["fbr_geometry"],
        "status": "partly supported",
        "detail": "The cited work varied size and shape, not modulus, and found "
                  "larger spheres provoked less fibrosis. Stiffness-driven "
                  "fibrosis is reported elsewhere; this reference does not carry it.",
    },
    {
        "claim": "Macrophages loaded with residue escape through new lymphatics to "
                 "regional nodes, where the waste is stored safely.",
        "evidence": REFS["tattoo_macrophage"],
        "status": "not shown by this reference",
        "detail": "The tattoo work shows pigment cycling between dermal macrophages "
                  "in place. Using it as evidence for lymphatic clearance overstates it. "
                  "The clearance route needs its own measurement.",
    },
]


def cocktail(material_key: str, products: list[str]) -> list[dict[str, Any]]:
    """The payloads the carrier has to deliver, and why each is there."""
    organic = material_key in {"PET", "PEF", "PLA", "PHA", "PBS", "PC", "PA"}
    out: list[dict[str, Any]] = [
        {
            "role": "Depolymerising enzyme",
            "what": "The catalyst selected above",
            "why": "Breaks the ester bonds in the fragment backbone",
            "evidence": MEASURED,
            "note": "The only component in this cocktail chosen from measured data.",
        },
        {
            "role": "Product capture",
            "what": "Chelator or host molecule sized to the released monomer",
            "why": f"Holds {', '.join(products) if products else 'the released monomer'} "
                   "so it does not reach the tissue",
            "evidence": DERIVED,
            "note": "The capacity it must have is fixed by mass balance; the chemistry "
                    "that provides it is not yet chosen.",
        },
        {
            "role": "Surface access",
            "what": "Biocompatible surfactant, plus a chelator for metal ions",
            "why": "A trauma fragment carries soil, blood and protein; the enzyme "
                   "cannot reach the polymer through that layer",
            "evidence": SPECIFIED,
            "note": "No measurement here. Whether the enzyme survives the surfactant "
                    "is an experiment, not an assumption.",
        },
        {
            "role": "Infection cover",
            "what": "Sustained-release broad-spectrum antibiotic",
            "why": "Degrading the fragment releases organisms that were sequestered on it",
            "evidence": SPECIFIED,
            "note": "Dose and release profile are unset.",
        },
        {
            "role": "Residue passivation",
            "what": "Hydrophilic polymer coating for undegraded mineral debris",
            "why": "Uncoated silica ruptures the lysosome of the macrophage that "
                   "engulfs it and drives sterile inflammation",
            "evidence": LITERATURE,
            "ref": REFS["silica_lysosome"],
            "note": "The mechanism is established. That a coating prevents it here is not.",
        },
    ]
    if not organic:
        out[0]["note"] = "No depolymerising enzyme applies to this material."
    return out


def carrier() -> list[dict[str, Any]]:
    """The hydrogel's required properties, each with the reason it is required."""
    return [
        {
            "property": "Injectable, then fixed in place",
            "spec": "Liquid through a needle; crosslinks at body temperature around the fragment",
            "why": "The point of the route is avoiding a surgical approach",
            "evidence": SPECIFIED,
        },
        {
            "property": "Does not swell",
            "spec": "Final volume equal to injected volume",
            "why": "A gel placed beside a nerve that takes up water becomes the "
                   "compression it was meant to prevent",
            "evidence": SPECIFIED,
            "note": "This is the property most likely to end the programme if it fails, "
                    "and the one with no number attached yet.",
        },
        {
            "property": "Holds the enzyme active",
            "spec": "Porous network that shields the protein from host proteases",
            "why": "A free enzyme in tissue is degraded long before a solid fragment is",
            "evidence": SPECIFIED,
            "note": "Retained activity inside the gel at 37 C in serum is unmeasured.",
        },
        {
            "property": "Captures what the enzyme releases",
            "spec": "Capacity at or above the mass-balance bound computed above",
            "why": "Monomer that escapes the carrier becomes a systemic exposure",
            "evidence": DERIVED,
        },
        {
            "property": "Geometry chosen deliberately",
            "spec": "Implant dimensions selected against the foreign-body literature",
            "why": "Implant size and shape measurably change the fibrotic response",
            "evidence": LITERATURE,
            "ref": REFS["fbr_geometry"],
        },
    ]


def host_response() -> list[dict[str, Any]]:
    """The foreign-body cascade, and where this product intends to interrupt it."""
    return [
        {"phase": "Minutes", "event": "Plasma proteins adsorb to the fragment surface and change conformation",
         "intervention": "A hydrophilic carrier surface reduces adsorption", "evidence": SPECIFIED},
        {"phase": "Hours to days", "event": "Neutrophils then inflammatory macrophages arrive",
         "intervention": "Released mediators intended to shift macrophage phenotype", "evidence": SPECIFIED},
        {"phase": "Weeks", "event": "Macrophages cannot engulf the fragment and fuse into giant cells",
         "intervention": "Reducing fragment mass removes the stimulus", "evidence": DERIVED},
        {"phase": "Months", "event": "Fibroblasts lay down a collagen capsule that contracts onto the nerve",
         "intervention": "Implant geometry chosen to reduce fibrosis", "evidence": LITERATURE,
         "ref": REFS["fbr_geometry"]},
    ]


def residue() -> dict[str, Any]:
    """What is left when the polymer phase is gone."""
    return {
        "summary": "Mineral inclusions and surface contamination are not enzyme "
                   "substrates and persist after the polymer is consumed.",
        "risk": {
            "what": "Uncoated silica particles rupture the lysosome of the macrophage "
                    "that engulfs them and activate the NALP3 inflammasome",
            "evidence": LITERATURE,
            "ref": REFS["silica_lysosome"],
        },
        "proposed": {
            "what": "Coat residue as it is exposed, and keep particle size a measured "
                    "endpoint of every degradation experiment",
            "evidence": SPECIFIED,
        },
        "open": "Where coated residue finally goes is unresolved. The tattoo-pigment "
                "literature is often cited for lymphatic clearance but shows pigment "
                "cycling between macrophages in place, so the clearance route has to "
                "be measured rather than assumed.",
        "ref": REFS["tattoo_macrophage"],
    }


def build(material_key: str, products: list[str]) -> dict[str, Any]:
    return {
        "cocktail": cocktail(material_key, products),
        "carrier": carrier(),
        "host_response": host_response(),
        "residue": residue(),
        "caveats": CAVEATS,
        "refs": REFS,
    }
