"""The metal arm: what shrapnel is actually made of, and what biology can touch.

The polymer arm selects a hydrolase that cleaves an ester bond. No enzyme does
that to a metal, and saying so was where this engine stopped. That was too
short an answer. Enzymes act on metals constantly, by electron transfer rather
than hydrolysis, and some of them are named and characterised.

What they do not act on is metallic iron. Cyc2 oxidises Fe(II) already in
solution; a siderophore dissolves an iron oxide; MnxG oxidises dissolved
Mn(II). All of them work downstream of corrosion, on the ion or the rust, not
on the lattice. So a metal fragment needs two stages where a polymer needed
one: something has to release the metal as an ion, and then biology has a
handle on it.

That is not a workaround. It is how the clinical literature already frames the
problem: the health effects of a retained fragment depend on "the chemical
composition and corrosiveness of the fragments in vivo" (PMID 24464236). The
fragment is corroding either way. The question this arm asks is whether that
can be directed and the products captured, instead of left to run into tissue.

One honest warning runs through all of it. Accelerating corrosion releases
metal ions into muscle, and for iron that means Fenton chemistry and oxidative
damage. Every route here is therefore a capture problem first and a
dissolution problem second, which inverts the polymer arm's priorities.
"""
from __future__ import annotations

from typing import Any

# Evidence classes, matching the rest of the engine. Nothing in this module is
# `measured`: no candidate here has been tested on a fragment in tissue, and
# labelling a literature-sourced enzyme as measured would be the exact error
# the polymer arm was built to prevent.
LITERATURE, SPECIFIED, ABSENT = "literature", "specified", "absent"


def _ref(pmid: str, doi: str, title: str, year: int, says: str) -> dict[str, Any]:
    return {"pmid": pmid, "doi": doi, "title": title, "year": year, "says": says}


REFS = {
    "fragment_chemistry": _ref(
        "24464236", "10.3390/ijerph110201261",
        "Embedded fragments from U.S. military personnel: chemical analysis and "
        "potential health implications",
        2014,
        "Modern blast wounds retain a wide range of metallic and composite "
        "material, and the health effects -- local and systemic toxicity, "
        "foreign-body reaction, malignancy -- depend on the composition and on "
        "the corrosiveness of the fragment in vivo. Corrosion is already the "
        "clinical variable; this arm asks whether it can be directed.",
    ),
    "craniocerebral_fragments": _ref(
        "41668569", "10.17116/neiro2026900116",
        "Composition and toxicity of shrapnel in mine-explosive and "
        "fragmentation craniocerebral wounds compared to titanium implants",
        2026,
        "Twelve projectiles removed from brain tissue were analysed by SEM with "
        "X-ray microanalysis; three were ferromagnetic and were taken forward "
        "for composition and cytotoxicity against a human cell line. Ferrous "
        "fragments in the head are not a hypothetical case.",
    ),
    "cyc2": _ref(
        "39937138", "10.1128/aem.01886-24",
        "Site-directed mutagenesis of the Cyc2 outer membrane protein from "
        "Acidithiobacillus ferrooxidans",
        2025,
        "Cyc2 is the outer-membrane cytochrome that oxidises Fe(II) to Fe(III) "
        "at the start of this organism's respiratory chain, and the residues "
        "that matter have been probed by mutagenesis -- so it is an engineerable "
        "protein, not just an observed activity.",
    ),
    "cyc2_activity": _ref(
        "23980744", "10.1007/s00253-013-5120-6",
        "Increases of ferrous iron oxidation activity by overexpression of Cyc2 "
        "in Acidithiobacillus ferrooxidans",
        2013,
        "Raising Cyc2 expression raised ferrous-iron oxidation activity, which "
        "ties the rate to this protein rather than to the organism as a whole.",
    ),
    "mnxg": _ref(
        "18165363", "10.1128/AEM.01915-07",
        "Direct identification of a bacterial manganese(II) oxidase, the "
        "multicopper oxidase MnxG",
        2008,
        "Identifies MnxG as the enzyme that oxidises Mn(II) to Mn(IV) oxide in "
        "bacterial spores. A named, isolated metal-oxidising enzyme.",
    ),
    "siderophore_dissolution": _ref(
        "25965980", "10.1021/acs.est.5b00725",
        "Synergistic effect of reductive and ligand-promoted dissolution of "
        "goethite",
        2015,
        "Reduction and chelation together dissolve an iron oxide faster than "
        "either alone. The mechanism a capture layer would rely on, measured on "
        "a mineral rather than on a fragment.",
    ),
    "mic_electron_transfer": _ref(
        "27134022", "10.1146/annurev-micro-102215-095418",
        "Mechanisms of bacterial extracellular electron exchange",
        2016,
        "Reviews how organisms move electrons across the cell envelope to and "
        "from insoluble substrates, which is the one mechanism that acts on "
        "metallic iron itself -- and it is a living biofilm, not an enzyme that "
        "can be injected.",
    ),
    "tungsten_alloy": _ref(
        "29051474", "10.1007/s12011-017-1144-6",
        "The role of the component metals in the toxicity of military-grade "
        "tungsten alloy",
        2015,
        "Attributes the toxicity of tungsten-alloy fragments to specific "
        "component metals rather than to tungsten alone, which is why an alloy "
        "cannot be reasoned about as if it were its headline element.",
    ),
}


# What fragments are made of, ordered by how often they turn up in wounds.
# `route` is what biology can offer, and for most of this table the answer is
# nothing: a passivating oxide is the same obstacle to an enzyme as it is to
# the surgeon's corrosion problem.
METALS: dict[str, dict[str, Any]] = {
    "steel": {
        "name": "Steel",
        "why_common": "Fragmentation casings and most improvised munitions. The "
                      "commonest retained fragment, and ferromagnetic, which is "
                      "what rules out MRI and makes the clinical bind.",
        "element": "Fe",
        "ferromagnetic": True,
        "route": "two_stage",
        "oxide": "Fe(II)/Fe(III) oxides, non-passivating -- rust flakes and "
                 "exposes fresh metal, which is why steel keeps corroding where "
                 "aluminium and titanium stop.",
        "enzymes": ["cyc2"],
        "capture": "siderophore or equivalent Fe(III) chelator",
        "evidence": LITERATURE,
    },
    "iron": {
        "name": "Iron",
        "why_common": "Low-alloy fragments and older ordnance; chemically the "
                      "same problem as steel with fewer alloying elements.",
        "element": "Fe",
        "ferromagnetic": True,
        "route": "two_stage",
        "oxide": "Same non-passivating oxide behaviour as steel.",
        "enzymes": ["cyc2"],
        "capture": "siderophore or equivalent Fe(III) chelator",
        "evidence": LITERATURE,
    },
    "copper": {
        "name": "Copper",
        "why_common": "Bullet jackets and driving bands; fragments often carry "
                      "a copper layer over a steel or lead core.",
        "element": "Cu",
        "ferromagnetic": False,
        "route": "two_stage",
        "oxide": "Cu(I)/Cu(II) oxides; corrodes in chloride-rich tissue fluid.",
        "enzymes": ["multicopper_oxidase"],
        "capture": "Cu(II) chelator; copper is redox-active and its free ion is "
                   "more toxic than iron's, so capture has to lead",
        "evidence": LITERATURE,
    },
    "lead": {
        "name": "Lead",
        "why_common": "Bullet cores and shot. The fragment with the best "
                      "documented systemic toxicity.",
        "element": "Pb",
        "ferromagnetic": False,
        "route": "capture_only",
        "oxide": "Carbonate and phosphate crusts; dissolves slowly, and faster "
                 "in a joint space, which is where the toxicity cases cluster.",
        "enzymes": [],
        "capture": "chelation, already clinical -- and the systematic review is "
                   "explicit that long-term chelation is not a substitute for "
                   "removal",
        "no_enzyme_reason": "Pb has no biological redox couple to exploit. "
                            "Nothing oxidises it usefully; there is no "
                            "lead-oxidising enzyme to engineer.",
        "evidence": SPECIFIED,
    },
    "aluminium": {
        "name": "Aluminium",
        "why_common": "Munition bodies and vehicle fragments.",
        "element": "Al",
        "ferromagnetic": False,
        "route": "none",
        "oxide": "A self-healing passivating Al2O3 film, which is the whole "
                 "reason aluminium survives in air and in tissue.",
        "enzymes": [],
        "no_enzyme_reason": "Al has one oxidation state in biology and no redox "
                            "chemistry to drive. The passivating film also "
                            "leaves nothing exposed to act on.",
        "evidence": ABSENT,
    },
    "titanium": {
        "name": "Titanium",
        "why_common": "Surgical implants, and increasingly in munitions. Used "
                      "as the inert control in fragment-toxicity work.",
        "element": "Ti",
        "ferromagnetic": False,
        "route": "none",
        "oxide": "TiO2, among the most stable passivating films known, which is "
                 "exactly why titanium is chosen for implants.",
        "enzymes": [],
        "no_enzyme_reason": "Deliberately inert. A route that dissolved "
                            "titanium would also dissolve every titanium "
                            "implant in the patient.",
        "evidence": ABSENT,
    },
    "tungsten": {
        "name": "Tungsten alloy",
        "why_common": "Armour-piercing munitions; typically alloyed with nickel "
                      "and cobalt, and its toxicity tracks those rather than "
                      "the tungsten.",
        "element": "W",
        "ferromagnetic": False,
        "route": "none",
        "oxide": "Tungstate forms slowly; the alloying metals dominate both the "
                 "corrosion and the toxicity.",
        "enzymes": [],
        "no_enzyme_reason": "No characterised tungsten-oxidising enzyme. The "
                            "alloy also cannot be treated as one element: its "
                            "nickel and cobalt behave differently from each "
                            "other and from the tungsten.",
        "evidence": ABSENT,
    },
}

ALIASES = {
    "fe": "iron", "ferrous": "iron", "carbon steel": "steel", "mild steel": "steel",
    "cu": "copper", "brass": "copper", "bronze": "copper",
    "pb": "lead", "al": "aluminium", "aluminum": "aluminium",
    "ti": "titanium", "w": "tungsten", "tungsten carbide": "tungsten",
}

# The candidate proteins. None is in the warehouse, because PAZy indexes
# polymer-degrading enzymes and these are not that. They are carried here as
# literature candidates with their mismatch stated, which is the same treatment
# the polymer arm gives a candidate whose optimum is wrong -- only the
# mismatches here are far larger.
ENZYMES: dict[str, dict[str, Any]] = {
    "cyc2": {
        "name": "Cyc2",
        "organism": "Acidithiobacillus ferrooxidans",
        "reaction": "Fe(II) -> Fe(III) + e-",
        "class": "outer-membrane cytochrome c",
        "acts_on": "dissolved Fe(II), not metallic iron",
        "refs": ["cyc2", "cyc2_activity"],
        # The reason this is hard, stated as the engine states a temperature gap.
        "mismatch": [
            {
                "kind": "pH",
                "measured": "native optimum near pH 2",
                "target": "pH 7.4",
                "detail": "A. ferrooxidans is an acidophile. This is a five-unit "
                          "gap, against the 0.6 units the polymer arm calls a "
                          "problem, and it is the single largest obstacle in "
                          "this arm.",
            },
            {
                "kind": "substrate state",
                "measured": "Fe(II) in acidic solution",
                "target": "Fe(II) released at a corroding surface at pH 7.4",
                "detail": "At neutral pH Fe(II) autoxidises in air within "
                          "minutes, so there may be little for the enzyme to "
                          "catalyse -- the abiotic reaction may already be "
                          "faster than the enzymatic one. That is the first "
                          "thing to measure, not to assume.",
            },
        ],
    },
    "multicopper_oxidase": {
        "name": "Multicopper oxidase (CueO class)",
        "organism": "various bacteria; human ceruloplasmin is the homologue",
        "reaction": "Cu(I) -> Cu(II), and broad metal oxidation",
        "class": "multicopper oxidase",
        "acts_on": "dissolved metal ions",
        "refs": ["mnxg"],
        "mismatch": [
            {
                "kind": "specificity",
                "measured": "characterised mostly on Cu and Mn",
                "target": "Cu released from a fragment surface",
                "detail": "The class is real and a human homologue already "
                          "handles copper in plasma, which helps the safety "
                          "case. What is missing is any measurement against a "
                          "corroding fragment.",
            },
        ],
    },
    "mnxg": {
        "name": "MnxG",
        "organism": "Bacillus sp. spores",
        "reaction": "Mn(II) -> Mn(IV) oxide",
        "class": "multicopper oxidase complex",
        "acts_on": "dissolved Mn(II)",
        "refs": ["mnxg"],
        "mismatch": [
            {
                "kind": "relevance",
                "measured": "Mn(II) oxidation",
                "target": "a fragment's manganese content",
                "detail": "Manganese is an alloying element in steel rather than "
                          "a fragment in its own right, so this is a supporting "
                          "activity for a steel fragment and not a route by "
                          "itself.",
            },
        ],
    },
}


def resolve(material: str) -> str | None:
    key = (material or "").strip().lower()
    key = ALIASES.get(key, key)
    return key if key in METALS else None


def route(material: str) -> dict[str, Any] | None:
    """The staged process for this metal, or the reason there is not one."""
    key = resolve(material)
    if key is None:
        return None
    m = METALS[key]
    out: dict[str, Any] = {
        "metal": key,
        "name": m["name"],
        "element": m["element"],
        "ferromagnetic": m["ferromagnetic"],
        "why_common": m["why_common"],
        "oxide": m["oxide"],
        "route": m["route"],
        "evidence": m["evidence"],
        "refs": [REFS["fragment_chemistry"]],
    }
    if m["ferromagnetic"]:
        out["refs"].append(REFS["craniocerebral_fragments"])

    if m["route"] == "none":
        out["stages"] = []
        out["why_not"] = m["no_enzyme_reason"]
        return out

    if m["route"] == "capture_only":
        out["stages"] = [{
            "n": 1,
            "stage": "Capture, with no dissolution step",
            "what": m["capture"],
            "evidence": SPECIFIED,
            "why": "Without a redox handle there is nothing to catalyse, so the "
                   "only biological contribution is holding what the fragment "
                   "releases on its own.",
        }]
        out["why_not"] = m["no_enzyme_reason"]
        return out

    # The two-stage route. Capture is stage 3 and is the part that must work
    # first: the dissolution stage is what makes the fragment dangerous.
    enzymes = [ENZYMES[e] for e in m["enzymes"] if e in ENZYMES]
    out["stages"] = [
        {
            "n": 1,
            "stage": "Controlled corrosion",
            "what": f"Release {m['element']} from the lattice as an ion, at a "
                    "rate the capture layer can keep up with.",
            "evidence": SPECIFIED,
            "why": "No enzyme acts on the metal itself. The fragment is already "
                   "corroding in tissue; this stage is about setting the rate "
                   "rather than starting the process.",
            "open": "How to set that rate locally, without a systemic "
                    "electrochemical effect, is unsolved and is the stage with "
                    "no candidate behind it.",
        },
        {
            "n": 2,
            "stage": "Enzymatic oxidation",
            "what": "Oxidise the released ion to the state the chelator binds.",
            "evidence": LITERATURE,
            "candidates": [
                {
                    "name": e["name"],
                    "organism": e["organism"],
                    "reaction": e["reaction"],
                    "acts_on": e["acts_on"],
                    "mismatch": e["mismatch"],
                    "refs": [REFS[r] for r in e["refs"]],
                }
                for e in enzymes
            ],
            "why": "This is where a named, characterised enzyme exists. It is "
                   "also where the engineering problem is, because the one for "
                   "iron comes from an organism that lives at pH 2.",
        },
        {
            "n": 3,
            "stage": "Capture",
            "what": m["capture"],
            "evidence": SPECIFIED,
            "why": "Inverted from the polymer arm. There, capture catches what "
                   "degradation releases. Here, released metal ions are the "
                   "hazard, so capture has to be in place and in excess before "
                   "stage 1 is allowed to run at all.",
            "refs": [REFS["siderophore_dissolution"]],
        },
    ]
    out["warning"] = {
        "claim": "Dissolving the fragment removes the hazard.",
        "status": "inverts it, until capture is proven",
        "detail": (
            f"A {m['name'].lower()} fragment is a local deposit. Dissolving it "
            "without capture converts a local problem into a systemic exposure, "
            "and for iron the released ion drives Fenton chemistry and oxidative "
            "damage in the surrounding muscle. Every milestone in this arm is "
            "therefore gated on capture capacity, not on dissolution rate."
        ),
    }
    out["alternative"] = {
        "what": "Microbially influenced corrosion is the one mechanism that acts "
                "on metallic iron directly, by extracellular electron transfer "
                "from Fe(0).",
        "why_not_used": "It is a living biofilm, not a protein that can be "
                        "injected, and deliberately establishing one in a wound "
                        "is not a therapy. It is listed because it is the reason "
                        "to believe the first stage is physically possible.",
        "evidence": LITERATURE,
        "ref": REFS["mic_electron_transfer"],
    }
    return out


def engineering_targets(material: str) -> list[dict[str, Any]]:
    """What would have to change in the enzyme for this to work at 37 C, pH 7.4.

    The polymer arm asks a lab to shift an optimum by 0.6 pH units. For iron
    the same question is five units, and pretending otherwise would be the most
    misleading thing this module could do. These are directions with a stated
    basis, not predictions.
    """
    key = resolve(material)
    if key is None or METALS[key]["route"] != "two_stage":
        return []
    if METALS[key]["element"] != "Fe":
        return [{
            "target": "Measure before engineering",
            "detail": "The copper route rests on a class rather than on one "
                      "characterised protein, so the first task is picking the "
                      "member, not modifying it.",
            "basis": SPECIFIED,
        }]
    return [
        {
            "target": "Move the active pH from 2 to 7.4",
            "detail": "Cyc2's surface and heme environment evolved for an "
                      "acidophile. Neutralising the net surface charge and "
                      "re-tuning the residues around the heme is the main body "
                      "of work, and site-directed mutagenesis on this protein "
                      "has already mapped which residues matter.",
            "basis": LITERATURE,
            "ref": REFS["cyc2"],
        },
        {
            "target": "Re-tune the heme redox potential for neutral pH",
            "detail": "The Fe(II)/Fe(III) couple shifts with pH, so a potential "
                      "tuned for pH 2 is mismatched at 7.4. This is a heme-"
                      "pocket problem and is the kind of change directed "
                      "evolution handles better than design.",
            "basis": SPECIFIED,
        },
        {
            "target": "Beat the abiotic reaction, or stop trying to",
            "detail": "At pH 7.4 Fe(II) autoxidises in air within minutes. If "
                      "the uncatalysed rate already exceeds what the enzyme adds, "
                      "the enzyme is the wrong component and the effort belongs "
                      "in the chelator instead. This is a measurement, and it "
                      "should be made before any mutagenesis.",
            "basis": SPECIFIED,
        },
        {
            "target": "Fuse the oxidase to the chelator",
            "detail": "Oxidation and capture happening at the same site would "
                      "stop Fe(III) diffusing into tissue between the two "
                      "stages. A fusion or a co-localised scaffold is the "
                      "obvious form; neither has been tried for this.",
            "basis": SPECIFIED,
        },
    ]
