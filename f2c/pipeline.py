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
    # --- added after the first two citations were found not to support the
    # claims they were attached to. Each was resolved against NCBI and its DOI
    # cross-checked against Crossref before being written here.
    "stiffness_trpv4": _ref(
        "41513093", "10.1016/j.jbc.2026.111135",
        "Transient receptor potential vanilloid four in macrophages mediates "
        "TGF-beta activation to drive myofibroblast differentiation and "
        "pulmonary fibrosis",
        2026,
        "Macrophage TRPV4 responds to matrix stiffness in the pathophysiologic "
        "range and optimises TGF-beta activation; deleting it in myeloid cells "
        "protected mice from fibrosis. A mechanism by which stiffness drives "
        "fibrosis through macrophages -- measured in lung, not against an "
        "implant.",
    ),
    "mechanical_cues": _ref(
        "37701130", "10.1016/j.mtbio.2023.100783",
        "Macrophages and fibroblasts in foreign body reactions: How mechanical "
        "cues drive cell functions?",
        2023,
        "Reviews stiffness and force as inputs to macrophage and fibroblast "
        "behaviour in the foreign-body reaction, and states plainly that the "
        "reported effects of mechanical cues on macrophage polarisation are "
        "inconsistent across studies.",
    ),
    "lead_toxicity": _ref(
        "36074021", "10.1080/15563650.2022.2116336",
        "Retained bullets and lead toxicity: a systematic review",
        2022,
        "142 articles. Lead toxicity from retained fragments is real but "
        "underdiagnosed, diagnosed months to years after the wound, and driven "
        "by fragment location, number and dwell time -- fragments in a fluid "
        "compartment carry the highest risk. No consensus exists on when to "
        "operate, and chelation alone is not an alternative to removal.",
    ),
    "lymphatic_drainage": _ref(
        "22580209", "10.1016/j.ejpb.2012.04.023",
        "A frustrating problem: accelerated blood clearance of PEGylated solid "
        "lipid nanoparticles following subcutaneous injection in rats",
        2012,
        "Colloidal particles injected subcutaneously drain preferentially into "
        "lymphatics and accumulate in regional nodes, and PEGylation increases "
        "that drainage. The same work shows a first PEGylated dose raises "
        "anti-PEG IgM that markedly accelerates clearance of later ones.",
    ),
    "enzyme_in_hydrogel": _ref(
        "37935291", "10.1016/j.ijbiomac.2023.127755",
        "Chitosan-based oral hydrogel formulations of beta-galactosidase to "
        "improve enzyme supplementation therapy for lactose intolerance",
        2023,
        "An enzyme covalently immobilised in a chitosan-PEG hydrogel survived "
        "gastric pH and retained 75% of its activity under subsequent "
        "intestinal conditions, protected from proteolysis. Evidence that a "
        "gel can keep an enzyme working in a hostile compartment -- the gut, "
        "not tissue at 37 C in serum.",
    ),
}

# Where the concept brief and the cited papers part company. Named here so the
# interface can show it rather than let a reviewer find it.
CAVEATS = [
    {
        "claim": "A soft hydrogel prevents the fibrotic capsule because macrophages "
                 "sense stiffness.",
        "evidence": REFS["fbr_geometry"],
        "status": "mechanism supported, this citation is the wrong one",
        "detail": "The originally cited work varied size and shape, not modulus, and "
                  "found larger spheres provoked less fibrosis -- it cannot carry a "
                  "stiffness claim. The mechanism does have support: macrophage TRPV4 "
                  "reads matrix stiffness and drives TGF-beta activation, and deleting "
                  "it in myeloid cells protects mice from fibrosis. That was measured "
                  "in lung fibrosis, not against an implant, and a review of mechanical "
                  "cues in the foreign-body reaction reports the polarisation results "
                  "as inconsistent between studies. So: plausible mechanism, real "
                  "evidence, not yet demonstrated for this application.",
        "also": [REFS["stiffness_trpv4"], REFS["mechanical_cues"]],
    },
    {
        "claim": "Macrophages loaded with residue escape through new lymphatics to "
                 "regional nodes, where the waste is stored safely.",
        "evidence": REFS["tattoo_macrophage"],
        "status": "route supported, 'safely' is not",
        "detail": "The tattoo work shows pigment cycling between dermal macrophages in "
                  "place and cannot support lymphatic clearance. The route itself is "
                  "documented elsewhere: colloidal particles injected subcutaneously "
                  "drain preferentially into lymphatics and accumulate in regional "
                  "nodes. That is drainage from subcutaneous tissue, not deep muscle, "
                  "and accumulating in a node is where the particles stop being "
                  "measured -- not evidence that they are harmless there.",
        "also": [REFS["lymphatic_drainage"]],
    },
    {
        "claim": "A PEG-based carrier is inert, so the treatment can be repeated if one "
                 "course does not clear the fragment.",
        "evidence": REFS["lymphatic_drainage"],
        "status": "contradicted",
        "detail": "A single PEGylated dose raised anti-PEG IgM that markedly accelerated "
                  "clearance of subsequent doses, by the subcutaneous route as much as "
                  "the intravenous one. The brief's carrier is HA-PEG and nothing in the "
                  "plan assumes one course suffices, so this is a risk to the programme "
                  "rather than a detail: repeat dosing may fail for immunological "
                  "reasons that have nothing to do with the enzyme.",
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
            "evidence": LITERATURE,
            "ref": REFS["enzyme_in_hydrogel"],
            "note": "The premise has a precedent: an enzyme covalently immobilised in a "
                    "chitosan-PEG gel kept 75% of its activity through gastric and then "
                    "intestinal conditions. That is a different hostile compartment. "
                    "Retained activity at 37 C in serum, against host proteases rather "
                    "than digestive ones, is still unmeasured here.",
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
        "open": "Where coated residue finally goes is partly answered. The tattoo-pigment "
                "literature, often cited here, shows pigment cycling between macrophages "
                "in place and does not demonstrate clearance. Drainage to regional nodes "
                "is documented for colloidal particles injected subcutaneously, and "
                "PEGylation increases it -- but that is subcutaneous tissue, not deep "
                "muscle, and arriving in a node is where those studies stop looking. "
                "Whether residue reaches a node from muscle, and what it does once there, "
                "are two separate measurements and neither has been made.",
        "ref": REFS["tattoo_macrophage"],
        "also": [REFS["lymphatic_drainage"]],
    }


def indication() -> dict[str, Any]:
    """Why leaving a fragment alone is itself a decision with a cost.

    The engine spent its evidence on which enzyme and how far it is from
    working. It never stated the case for intervening at all, which left the
    most basic question a reviewer can ask -- why not just leave it? --
    answered by assertion. The systematic review below answers it from 142
    papers, and is careful about what is not known, which is the part worth
    carrying.
    """
    return {
        "problem": "A retained fragment is not inert. Lead from retained bullets "
                   "causes systemic toxicity that is real but underdiagnosed, and "
                   "is typically recognised months to years after the injury.",
        "evidence": LITERATURE,
        "ref": REFS["lead_toxicity"],
        "risk_factors": [
            "Fragments sitting in a fluid compartment, such as a joint space, "
            "carry substantially higher risk.",
            "Risk rises with the number of fragments, an associated fracture, "
            "and how long the fragment has been in place.",
        ],
        "why_a_gap_exists": (
            "The same review found no consensus on when to monitor, chelate or "
            "operate, and concluded that long-term chelation is not a substitute "
            "for removal. That is the space this product is aimed at: fragments "
            "where surgery is the only established answer and the approach itself "
            "is the risk."
        ),
        "honest_limit": (
            "This evidence is about lead. It establishes that retained fragments "
            "can harm and that removal is sometimes the only option, not that an "
            "enzymatic route is the right alternative, and not anything about the "
            "polymer fragments this engine selects catalysts for."
        ),
    }


def build(material_key: str, products: list[str]) -> dict[str, Any]:
    return {
        "indication": indication(),
        "cocktail": cocktail(material_key, products),
        "carrier": carrier(),
        "host_response": host_response(),
        "residue": residue(),
        "caveats": CAVEATS,
        "refs": REFS,
    }
