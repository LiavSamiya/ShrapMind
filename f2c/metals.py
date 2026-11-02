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

import json
from pathlib import Path
from typing import Any

# Evidence classes, matching the rest of the engine. Nothing in this module is
# `measured`: no candidate here has been tested on a fragment in tissue, and
# labelling a literature-sourced enzyme as measured would be the exact error
# the polymer arm was built to prevent.
LITERATURE, SPECIFIED, DERIVED, ABSENT = (
    "literature", "specified", "derived", "absent")


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
    "ferritin": _ref(
        "9003196", "10.1074/jbc.272.5.2846",
        "Human ferritin heavy chain: ferroxidase activity and iron deposition",
        1997,
        "Human ferritin heavy chain catalyses 4 Fe(2+) + O2 + 4 H(+) -> "
        "4 Fe(3+) + 2 H2O and deposits the product as ferric hydroxide inside a "
        "24-subunit shell about 12 nm across. UniProt's own summary is that it "
        "stores iron 'in a soluble, non-toxic form' -- oxidation and capture in "
        "one human protein, with 145 solved structures (P02794).",
    ),
    "ceruloplasmin": _ref(
        "9159481", "10.1073/pnas.93.9.4280",
        "Ceruloplasmin, the human plasma multicopper ferroxidase",
        1996,
        "The circulating human ferroxidase, a multicopper oxidase that acts on "
        "both iron and copper. Endogenous, which is why the copper route starts "
        "here rather than at a fungal laccase (P00450).",
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
    "ligand_dissolution": _ref(
        "25965980", "10.1021/acs.est.5b01191",
        "Synergistic effect of reductive and ligand-promoted dissolution of "
        "goethite",
        2015,
        "The mechanism stage 1 was missing. Dissolution of an iron oxide is "
        "driven by taking the product away: the rate coefficient tracks the "
        "stability constant of the Fe(III)-ligand complex, so the chelator sets "
        "the rate. Desferrioxamine B and ascorbate together dissolve faster "
        "than the sum of either alone, and the synergy is strongest under "
        "oxygen. Ascorbate by itself does nothing in air, because the Fe(II) it "
        "makes is reoxidised immediately. Measured on goethite at pH 6, not on "
        "metallic iron.",
    ),
    "no_siderophore_on_metal": _ref(
        "", "",
        "Searched: siderophore or chelator against zerovalent / metallic iron",
        2026,
        "PubMed returns nothing for chelator-driven dissolution of metallic "
        "iron. The oxide case is well studied and the metal case is not, which "
        "is the honest boundary of this route and the reason stage 1 starts at "
        "the fragment's existing rust layer rather than at the metal.",
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


# ---------------------------------------------------------------------------
# The candidate set, assembled from EC classes by tools/fetch_metal_candidates.py
# because no PAZy equivalent exists for metals. 344 reviewed entries, of which
# 23 are human.
#
# Ranking here is not the polymer arm's weighted score, and should not pretend
# to be: there are no kinetic measurements to weigh. It is a sort on the three
# things that decide whether a protein could ever be given to a patient --
# whether it is human, whether its structure is solved, and whether it both
# oxidises and stores. Those are facts about the entry, not estimates.
# ---------------------------------------------------------------------------
CANDIDATES_PATH = Path(__file__).resolve().parent.parent / "data" / "metal_candidates.json"


def load_candidates() -> dict[str, Any]:
    if not CANDIDATES_PATH.exists():
        return {"candidates": [], "queries": {}, "fetched_at": None}
    return json.loads(CANDIDATES_PATH.read_text())


def rank_candidates(element: str, limit: int = 8) -> list[dict[str, Any]]:
    """Candidates for this element, most usable first.

    'Usable' means something specific and checkable: a human protein needs no
    immunosuppression argument, a solved structure means engineering can start
    from coordinates rather than a prediction, and a ferritin removes the
    diffusion gap between oxidation and capture by doing both inside one shell.
    """
    wanted = {"Fe": {"ferroxidase", "ferroxidase_bacterial"},
              "Cu": {"multicopper_oxidase"},
              "Mn": {"multicopper_oxidase"}}.get(element, set())
    if not wanted:
        return []
    # Ceruloplasmin is filed under ferroxidase but is a multicopper oxidase
    # that handles both metals, so it belongs in the copper list too. Named
    # explicitly rather than by widening the class set, which would have
    # dragged every ferritin into a copper answer.
    SPANS_BOTH = {"P00450"}

    out = []
    for c in load_candidates().get("candidates", []):
        if not wanted.intersection(c.get("classes") or []) \
                and c["accession"] not in SPANS_BOTH:
            continue
        # Isoform records duplicate their parent and add nothing to choose by.
        if "-" in c["accession"]:
            continue
        human = c["organism"] == "Homo sapiens"
        name = (c.get("name") or "").lower()
        stores = "ferritin" in name
        out.append({
            **c,
            "human": human,
            "stores_as_well_as_oxidises": stores,
            "structures": len(c.get("pdb_ids") or []),
        })
    out.sort(key=lambda c: (not c["human"], not c["stores_as_well_as_oxidises"],
                            -c["structures"], c["accession"]))
    return out[:limit]


# ---------------------------------------------------------------------------
# Mass balance, the metal arm's version.
#
# The polymer arm derives a capture requirement from mass without touching
# kinetics, and refuses to state a rate. The same split applies here, and it
# was the calculation to do before any biology: if a fragment needs an absurd
# quantity of protein, the route is dead on arithmetic alone.
#
# It is not absurd. A 24-subunit ferritin shell holds on the order of 4500 iron
# atoms, so a 50 mg steel fragment needs roughly 1.8 times its own mass in
# protein -- a ratio that holds at every fragment size, because both scale
# linearly with iron content. Even at a pessimistic 1000 atoms per shell it is
# about eight times, which is a formulation problem rather than an impossible
# one.
# ---------------------------------------------------------------------------
AVOGADRO = 6.02214076e23
FE_G_PER_MOL = 55.845
CU_G_PER_MOL = 63.546
# Order of magnitude for a loaded 24-mer. Reported ranges run to ~4500, and the
# figure is carried as an assumption rather than a measurement because the
# loading achieved in a carrier is exactly what nobody has measured.
FE_ATOMS_PER_SHELL = 4500
FERRITIN_SHELL_KDA = 474.0
# Fraction of fragment mass that is the target metal. Carbon steel is nearly
# all iron; a jacketed fragment is a composite and its copper fraction depends
# on the round, so copper is left unset rather than guessed.
METAL_FRACTION = {"steel": 0.98, "iron": 1.0}


def capacity(material: str, mass_mg: float | None) -> dict[str, Any]:
    """How much capture the fragment demands, derived from mass alone."""
    key = resolve(material)
    if key is None or mass_mg is None or mass_mg <= 0:
        return {"computable": False,
                "reason": "needs a recognised metal and a fragment mass"}
    fraction = METAL_FRACTION.get(key)
    element = METALS[key]["element"]
    if fraction is None or element != "Fe":
        return {
            "computable": False,
            "reason": (
                f"{METALS[key]['name']} fragments are composites and the "
                f"{element} fraction depends on the round, so the molar "
                "quantity cannot be bounded from mass. Characterise the "
                "fragment first, as the polymer arm says for an uncharacterised "
                "polymer."
            ),
        }

    grams = mass_mg / 1000.0 * fraction
    moles = grams / FE_G_PER_MOL
    atoms = moles * AVOGADRO
    shells = atoms / FE_ATOMS_PER_SHELL
    protein_mg = shells * (FERRITIN_SHELL_KDA * 1000) / AVOGADRO * 1000

    return {
        "computable": True,
        "element": element,
        "metal_fraction": fraction,
        "mmol_metal": moles * 1000,
        "atoms": atoms,
        "shells_needed": shells,
        "ferritin_mg": protein_mg,
        "ratio_to_fragment": protein_mg / mass_mg,
        "assumption": (
            f"{FE_ATOMS_PER_SHELL} Fe atoms per 24-subunit shell, which is an "
            "order-of-magnitude figure and the one number here that is assumed "
            "rather than derived. Loading achieved inside a carrier is exactly "
            "what has not been measured."
        ),
        "sensitivity": [
            {"atoms_per_shell": cap,
             "ferritin_mg": round(atoms / cap * (FERRITIN_SHELL_KDA * 1000)
                                  / AVOGADRO * 1000, 1)}
            for cap in (1000, 2000, FE_ATOMS_PER_SHELL)
        ],
        "basis": "Fragment mass and iron's atomic mass. No kinetic assumption.",
        "rate": (
            "Not derivable. How fast the fragment releases iron at 37 C under a "
            "protein corona is unmeasured, exactly as turnover on a solid "
            "polymer is."
        ),
    }


# What the hydrogel has to do in this arm, which is more than it does in the
# polymer one. There the gel holds an enzyme near a substrate it can reach.
# Here the enzyme cannot reach the fragment at all -- ferritin works inside
# cells and the metal corrodes outside them -- so the gel is the only thing
# that puts the two in contact, and it has to hold roughly twice the
# fragment's mass in protein while doing it.
CARRIER_REQUIREMENTS = [
    {
        "property": "Holds the capture protein at the surface",
        "spec": "Ferritin immobilised in the network, pores facing the metal, "
                "at the loading the mass balance above demands.",
        "why": "Ferritin is a cytosolic protein and the fragment is "
               "extracellular. Without the gel there is no contact at all, "
               "which makes this the load-bearing component of the whole arm "
               "rather than a delivery convenience.",
        "evidence": SPECIFIED,
        "note": "Nothing here is measured. Ferritin nanocages are an "
                "established delivery vehicle, which is why this is treated as "
                "a formulation problem, but no one has loaded one into a gel "
                "against a corroding fragment.",
    },
    {
        "property": "Carries capture capacity in excess, before anything dissolves",
        "spec": "At or above the ferritin mass the balance gives, in place "
                "before stage 1 is allowed to start.",
        "why": "The released ion is the hazard. In the polymer arm capture "
               "catches what degradation releases; here it has to be waiting.",
        "evidence": DERIVED,
    },
    {
        "property": "Does not swell",
        "spec": "Final volume equal to injected volume.",
        "why": "Unchanged from the polymer arm and still the property most "
               "likely to end the programme: a gel beside a nerve that takes up "
               "water becomes the compression it was placed to prevent.",
        "evidence": SPECIFIED,
        "note": "Still no number attached, in either arm.",
    },
    {
        "property": "Keeps the loaded protein from unloading",
        "spec": "Retain Fe(III) inside the shell until the carrier is cleared.",
        "why": "Ferritin releases iron on demand inside a cell. Here it must "
               "not, and a gel that lets loaded shells leak has moved the "
               "hazard rather than removed it.",
        "evidence": SPECIFIED,
    },
    {
        "property": "Survives a corroding surface",
        "spec": "Stable against the local pH shift and the oxidants corrosion "
                "produces.",
        "why": "Iron corrosion changes the chemistry immediately around it. A "
               "gel tuned for neutral tissue may not be sitting in neutral "
               "tissue once stage 1 runs.",
        "evidence": SPECIFIED,
        "note": "Not a concern the polymer arm has, because ester hydrolysis "
                "does not acidify its own neighbourhood the way corrosion does.",
    },
]


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
            "stage": "Chelation-driven dissolution",
            "what": "Pull Fe(III) off the oxide surface with a high-affinity "
                    "chelator, with ascorbate as a reductant alongside it.",
            "evidence": LITERATURE,
            "why": "Nothing is added to make the fragment rust. Dissolution is "
                   "driven by removing the product: strip Fe(III) from the "
                   "surface and the equilibrium pulls more off behind it. The "
                   "rate coefficient tracks the stability constant of the "
                   "Fe(III)-ligand complex, so the chelator chosen sets the "
                   "rate, from a published number rather than an experiment.",
            "self_limiting": (
                "This is the property that answers the arm's own warning. "
                "Dissolution proceeds only as fast as there is unoccupied "
                "chelator, so it cannot outrun its own capture and cannot run "
                "away into systemic exposure. Capture and accelerant are the "
                "same molecule, which is why the hazard is bounded by design "
                "rather than by dosing care."
            ),
            "candidates": [
                {
                    "name": "Desferrioxamine B (deferoxamine)",
                    "organism": "Streptomyces pilosus siderophore; an approved drug",
                    "reaction": "Fe(III) + DFOB -> ferrioxamine, K_stability ~10^30",
                    "acts_on": "dissolved Fe(III) and the oxide surface",
                    "mismatch": [
                        {
                            "kind": "substrate",
                            "measured": "goethite, an iron oxide, at pH 6",
                            "target": "the oxide layer on a metallic fragment at pH 7.4",
                            "detail": "A retained fragment is already covered in "
                                      "that oxide, so the measured case is the "
                                      "fragment's own surface. Whether "
                                      "dissolution continues into the metal "
                                      "beneath is unmeasured -- PubMed returns "
                                      "nothing for a chelator against metallic "
                                      "iron.",
                        },
                    ],
                    "advantage": "Already licensed for iron overload, which "
                                 "removes a whole regulatory arm: the question "
                                 "becomes route and formulation rather than a "
                                 "new molecular entity.",
                },
                {
                    "name": "Ascorbate",
                    "organism": "not biological in origin; vitamin C",
                    "reaction": "Fe(III) -> Fe(II), reductive dissolution",
                    "acts_on": "the oxide surface, only alongside a chelator",
                    "mismatch": [
                        {
                            "kind": "works alone",
                            "measured": "no dissolution under oxic conditions by itself",
                            "target": "a contribution in oxygenated tissue",
                            "detail": "The Fe(II) it produces is reoxidised "
                                      "immediately in air, so ascorbate alone "
                                      "achieves nothing. Its whole value is the "
                                      "synergy with the chelator, which was "
                                      "strongest under oxygen -- the condition "
                                      "tissue actually provides.",
                        },
                    ],
                },
            ],
            "refs": [REFS["ligand_dissolution"], REFS["no_siderophore_on_metal"]],
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
            "why": "This is the stage with real candidates behind it, and the "
                   "only one that does. Ranked on what decides whether a "
                   "protein could reach a patient: human origin, a solved "
                   "structure, and whether it stores what it oxidises.",
            "ranked": rank_candidates(m["element"]),
        },
        {
            "n": 3,
            "stage": "Capture",
            "what": m["capture"],
            "evidence": SPECIFIED,
            "why": "Inverted from the polymer arm, and then collapsed into "
                   "stage 1. There, capture catches what degradation releases. "
                   "Here the chelator that drives dissolution is the thing that "
                   "holds the product, so capture is not a later stage waiting "
                   "to catch up -- it is the same molecule, and the ferritin "
                   "below is the second line for what the chelator hands on.",
            "refs": [REFS["ligand_dissolution"]],
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
    out["carrier"] = CARRIER_REQUIREMENTS
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
    """What would have to change for this to work in tissue.

    These were written when Cyc2 was the only candidate I could name, and they
    read accordingly: move an optimum five pH units, re-tune a heme pocket,
    fight an acidophile's chemistry into a neutral body. Querying EC 1.16.3
    instead of recalling the literature produced a better lead and most of that
    work disappeared with it.

    Human ferritin oxidises Fe(II) and stores the Fe(III) inside its own shell,
    at the pH of human cytosol, with 145 solved structures. It is already the
    fusion of oxidation and capture that the Cyc2 route listed as an
    aspiration, and being human it needs no argument about immunogenicity. So
    the remaining targets are about delivery and capacity, not about dragging
    an enzyme across five pH units.
    """
    key = resolve(material)
    if key is None or METALS[key]["route"] == "none":
        return []
    element = METALS[key]["element"]

    if element == "Fe":
        return [
            {
                "target": "Load ferritin where the fragment is",
                "detail": "Ferritin works inside cells; the fragment corrodes "
                          "outside them. The protein does not need changing so "
                          "much as placing -- in the carrier, at the surface, "
                          "with its pores facing the metal. Ferritin nanocages "
                          "are already an established delivery vehicle, which "
                          "is the reason to think this is formulation rather "
                          "than protein engineering.",
                "basis": LITERATURE,
                "ref": REFS["ferritin"],
            },
            {
                "target": "Match capacity to the fragment, by mass balance",
                "detail": "A 24-subunit shell holds on the order of thousands "
                          "of iron atoms. The fragment's mass gives the moles "
                          "of iron exactly, as it does for a polymer, so the "
                          "number of shells needed is arithmetic rather than an "
                          "estimate. This is the calculation to do first, "
                          "because if it comes out absurd the route is dead "
                          "before any biology is attempted.",
                "basis": SPECIFIED,
            },
            {
                "target": "Decide whether the enzyme is needed at all",
                "detail": "At pH 7.4 Fe(II) autoxidises in air within minutes. "
                          "If the uncatalysed reaction already outpaces the "
                          "enzyme, ferritin's value is entirely in the storing "
                          "and none of it in the oxidising -- which would make "
                          "this a chelation problem with a protein-shaped "
                          "container, and would simplify the programme. "
                          "Measure before engineering.",
                "basis": SPECIFIED,
            },
            {
                "target": "Keep the shell from unloading in tissue",
                "detail": "Ferritin releases iron on demand in a cell; here it "
                          "must not. Stabilising the loaded shell, or clearing "
                          "it before it is asked to release, is the safety "
                          "question that replaces the old pH problem.",
                "basis": SPECIFIED,
            },
            {
                "target": "Keep Cyc2 as the rate option, not the lead",
                "detail": "If measurement shows oxidation really is the "
                          "bottleneck, Cyc2 oxidises iron far faster than a "
                          "ferroxidase does -- and then its five-unit pH gap "
                          "has to be paid for. It is the fallback, and the "
                          "reason to keep the mutagenesis literature to hand.",
                "basis": LITERATURE,
                "ref": REFS["cyc2"],
            },
        ]

    if element == "Cu":
        return [
            {
                "target": "Start from ceruloplasmin, not from a laccase",
                "detail": "Ceruloplasmin is the human plasma multicopper "
                          "oxidase and already handles copper in circulation, "
                          "so the safety case starts from an endogenous "
                          "protein. The fungal laccases have more structures "
                          "and more activity, and would need everything "
                          "ceruloplasmin does not.",
                "basis": LITERATURE,
                "ref": REFS["ceruloplasmin"],
            },
            {
                "target": "Capture before oxidation, for copper especially",
                "detail": "Free copper is more redox-active than free iron, so "
                          "the ion released by a jacketed fragment is more "
                          "dangerous than iron's. Nothing about the dissolution "
                          "stage should be attempted until the chelator is "
                          "demonstrated.",
                "basis": SPECIFIED,
            },
        ]

    return [{
        "target": "Measure before engineering",
        "detail": "This metal has a route but no characterised lead, so the "
                  "first task is finding the protein, not modifying one.",
        "basis": SPECIFIED,
    }]
