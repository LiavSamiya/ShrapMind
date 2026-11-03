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
import math
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
        "9003196", "10.1021/bi961830l",
        "Dinuclear center of ferritin: studies of iron binding and oxidation "
        "show differences in the two iron sites",
        1997,
        "Studies the dinuclear ferroxidase centre itself and shows the two "
        "iron sites behave differently during binding and oxidation. The "
        "mechanism, in other words, not the summary. The stoichiometry "
        "(4 Fe(2+) + O2 + 4 H(+) -> 4 Fe(3+) + 2 H2O), the 24-subunit 12 nm "
        "shell and the phrase 'stores iron in a soluble, non-toxic form' are "
        "UniProt P02794's annotations, and are cited to UniProt rather than to "
        "this paper.",
    ),
    "ceruloplasmin": _ref(
        "21315066", "10.1016/j.cca.2011.02.003",
        "Association of haptoglobin phenotypes with ceruloplasmin ferroxidase "
        "activity in beta-thalassemia major",
        2011,
        "Measures ceruloplasmin's ferroxidase activity in patients, which "
        "establishes the activity rather than explaining it. For the protein's "
        "identity as the human plasma multicopper oxidase the source is "
        "UniProt P00450, not a paper -- and saying so is more honest than "
        "attaching a citation that does not carry the claim.",
    ),
    "cyc2": _ref(
        "39937138", "10.1002/smll.202408837",
        "Site-directed mutagenesis of the Cyc2 outer membrane protein from "
        "Acidithiobacillus ferrooxidans",
        2025,
        "Cyc2 is the outer-membrane cytochrome that oxidises Fe(II) to Fe(III) "
        "at the start of this organism's respiratory chain, and the residues "
        "that matter have been probed by mutagenesis -- so it is an engineerable "
        "protein, not just an observed activity.",
    ),
    "cyc2_activity": _ref(
        "23980744", "10.1002/bab.1110",
        "Increases of ferrous iron oxidation activity by overexpression of Cyc2 "
        "in Acidithiobacillus ferrooxidans",
        2013,
        "Raising Cyc2 expression raised ferrous-iron oxidation activity, which "
        "ties the rate to this protein rather than to the organism as a whole.",
    ),
    "mnxg": _ref(
        "18165363", "10.1128/AEM.01240-07",
        "Direct identification of a bacterial manganese(II) oxidase, the "
        "multicopper oxidase MnxG",
        2008,
        "Identifies MnxG as the enzyme that oxidises Mn(II) to Mn(IV) oxide in "
        "bacterial spores. A named, isolated metal-oxidising enzyme.",
    ),
    "iron_corrodes_too_slowly": _ref(
        "27598975", "10.1021/acsami.6b07068",
        "Accelerated degradation behavior and cytocompatibility of pure iron "
        "treated with sandblasting",
        2016,
        "States the opposite of this arm's own warning: iron's corrosion rate "
        "in a biological environment 'may be too slow for the targeted "
        "applications'. Sandblasting raised it and the increase persisted "
        "through long-term immersion, which identifies surface state rather "
        "than chemistry as the lever. The engineering problem with iron in "
        "tissue is making it corrode at all, not stopping it.",
    ),
    "chelating_hydrogel": _ref(
        "41885000", "10.1002/adhm.202505864",
        "Ion-chelating hydrogel regulates porous zinc scaffold degradation for "
        "osteoimmune bone repair",
        2026,
        "Published precedent for this arm's whole architecture: a hydrogel "
        "whose hydroxyl and carboxyl groups chelate the released metal ion to "
        "regulate corrosion kinetics and stabilise ion release, in vivo. Zinc "
        "rather than iron, and a scaffold placed deliberately rather than a "
        "fragment to be removed -- but the chelating gel controlling a "
        "corroding metal is not hypothetical.",
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
    "iron_homeostasis": _ref(
        "38489995", "10.1016/j.jnha.2024.100212",
        "Iron homeostasis in older adults: balancing nutritional requirements "
        "and health risks",
        2024,
        "The fact the readout rests on: human iron excretion is inefficient "
        "and not highly regulated, so the body controls iron by absorption "
        "rather than by disposal. Losses are passive -- epithelial turnover, "
        "blood loss, skin. There is no physiological route that clears iron "
        "on demand, which is why chelator-bound iron appearing in urine is a "
        "signal against a near-silent background.",
    ),
    "chelation_urinary": _ref(
        "15720959", "",
        "Iron chelation therapy",
        2005,
        "Deferoxamine's mode of clearance is urinary excretion of the "
        "chelated iron, and the review distinguishes chelators on exactly "
        "that basis. So the product's own chelator already carries the "
        "readout: whatever it captures leaves in the urine, where it can be "
        "counted.",
    ),
    "extracellular_hydrogenase": _ref(
        "30310166", "10.1038/s41598-018-33541-5",
        "An extracellular [NiFe] hydrogenase mediating iron corrosion is "
        "encoded in a genetically unstable genomic island in Methanococcus "
        "maripaludis",
        2018,
        "The paper that overturns this arm's assumption that nothing but a "
        "biofilm attacks metallic iron. A 12-kb 'MIC island' encodes a [NiFe] "
        "hydrogenase together with the TatA/TatC machinery that secretes it "
        "and its maturation protease, so the enzyme reaches the outside of the "
        "cell and contacts Fe(0) directly: Fe(0) + 2 H+ -> Fe(2+) + H2. A "
        "deletion mutant lost the corroding activity. This is a secreted "
        "protein acting on solid metal, not a community of cells.",
    ),
    "cell_free_electron_uptake": _ref(
        "25900658", "10.1128/mBio.00496-15",
        "Extracellular enzymes facilitate electron uptake in biocorrosion and "
        "bioelectrosynthesis",
        2015,
        "And the demonstration that the cells are not needed at all. Free, "
        "surface-associated hydrogenases and presumably formate "
        "dehydrogenases, released from Methanococcus maripaludis during "
        "ordinary culture, catalyse H2 or formate formation when sorbed to a "
        "redox-active surface -- and rates from cell-free spent medium were "
        "sufficient to account for the methane formed from Fe(0). A mutant "
        "lacking every catabolic hydrogenase still showed it. Cell-free "
        "activity on metallic iron is the result this arm said did not exist.",
    ),
    "mic_electron_transfer": _ref(
        "27134022", "10.1016/bs.ampbs.2016.02.002",
        "Mechanisms of bacterial extracellular electron exchange",
        2016,
        "Reviews how organisms move electrons across the cell envelope to and "
        "from insoluble substrates, which is the one mechanism that acts on "
        "metallic iron itself -- and it is a living biofilm, not an enzyme that "
        "can be injected.",
    ),
    "tungsten_alloy": _ref(
        "29051474", "10.3390/toxics3040499",
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
        "which_steel": (
            "Carbon and low-alloy steel specifically. Stainless is a separate "
            "entry and a separate answer: above about 10.5% chromium the alloy "
            "passivates and this entire route stops working. Treating 'steel' "
            "as one material was an error in this engine, and it is the error "
            "most likely to matter in a real patient, because ball bearings "
            "packed into a device are often stainless."
        ),
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
    "stainless": {
        "name": "Stainless steel",
        "why_common": "Ball bearings and nuts packed into improvised devices, "
                      "and any surgical hardware already in the patient. Not a "
                      "rare case: bearings are among the commonest "
                      "penetrating fragments in a blast injury.",
        "element": "Fe",
        "ferromagnetic": True,   # true for the martensitic and ferritic grades
        "route": "none",
        "oxide": "Chromium(III) oxide. Dense, adherent and self-healing -- "
                 "the opposite of rust in every property that matters here.",
        "enzymes": [],
        "capture": "not reached; nothing is released to capture",
        "no_enzyme_reason": (
            "Stainless is passivating, and that single fact moves it out of "
            "this arm and in beside aluminium and titanium. At or above about "
            "10.5% chromium the alloy grows a Cr2O3 film a few nanometres "
            "thick that is dense rather than flaky, adherent rather than "
            "spalling, and re-forms within seconds wherever it is scratched. "
            "The whole iron route depends on the opposite behaviour: rust "
            "flakes, fresh metal is exposed, tissue re-oxidises it, and the "
            "chelator takes the next layer. Against Cr2O3 there is no next "
            "layer. Deferoxamine is also selective for Fe(III) and does not "
            "meaningfully lift chromium oxide, so the chelator that drives "
            "the carbon-steel route does nothing here."
        ),
        "why_this_matters_clinically": (
            "A surgeon cannot tell carbon steel from stainless by looking at "
            "a radiograph, and this engine was treating them as one material. "
            "They are not one material: the same treatment that slowly "
            "debulks a carbon-steel fragment does nothing at all to a "
            "stainless bearing. Any trial has to establish fragment "
            "composition as an inclusion criterion, not discover it "
            "afterwards."
        ),
        "how_to_tell": (
            "Retrieved fragments go to XRF or SEM-EDS, which is routine and "
            "fast. In situ it is harder: dual-energy CT separates some alloys, "
            "and a stainless fragment is usually less MRI-hostile than a "
            "carbon-steel one because many bearing grades are austenitic and "
            "only weakly magnetic. Neither is definitive, and the honest "
            "position is that composition is unknown before retrieval."
        ),
        "evidence": SPECIFIED,
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
        "but_there_is_a_pathway": (
            "Just not a shrinking one, and the team's clinical review draws "
            "the distinction this arm was missing. Phosphatases, ureases and "
            "carbonic anhydrase all act on Pb(2+): they raise local phosphate "
            "or carbonate and precipitate it as pyromorphite, "
            "Pb5(PO4)3Cl, or as cerussite. That is biomineralisation, and it "
            "is real -- one 2026 study reports up to 99% removal of Pb(2+) "
            "from solution with carbonic anhydrase. What it does is lock the "
            "ion into an insoluble mineral, which lowers mobility and "
            "toxicity. It does not make the fragment smaller. "
            "DETOXIFICATION IS NOT SHRINKAGE, and conflating them would be "
            "the most inviting error available in this arm: a route with "
            "genuine enzymes, genuine products and no effect on the thing the "
            "patient came in with."
        ),
        "the_one_metallic_lead_precedent": (
            "Paecilomyces javanicus transforms metallic lead shot to "
            "pyromorphite on the metal surface, through fungal biocorrosion "
            "coupled to phosphate-mediated mineralisation. It is the closest "
            "anything comes to acting on Pb(0) -- and no single enzyme was "
            "isolated from it, so there is nothing to put in a hydrogel. "
            "Named because it is the honest state of the art, not because it "
            "is a lead."
        ),
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
    "stainless steel": "stainless", "inox": "stainless", "ss": "stainless",
    "304": "stainless", "316": "stainless", "316l": "stainless",
    "ball bearing": "stainless", "surgical steel": "stainless",
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
# What a fragment is actually made of, by element.
#
# This started as METAL_FRACTION = {"steel": 0.98}, which carried the iron and
# silently discarded the other 2%. That 2% is where the alloying elements
# live, and two of them -- nickel and chromium -- are recognised contact
# allergens that the chelator does not capture, because deferoxamine is
# selective for Fe(III). Dissolving a fragment releases everything in it, not
# only the metal the route was designed around.
#
# The compositions below are nominal ranges for the grade, not measurements of
# anyone's fragment, and they are labelled as such wherever they are used.
# Stage 1 of the protocol exists to replace them with XRF on the real thing.
COMPOSITION: dict[str, dict[str, float]] = {
    # Low-carbon fragmentation steel. Manganese and silicon are deliberate
    # additions; the balance is iron.
    "steel": {"Fe": 0.980, "Mn": 0.012, "Si": 0.005, "C": 0.002, "P": 0.001},
    "iron": {"Fe": 1.0},
    # Austenitic stainless, for completeness. The route refuses it on
    # passivation grounds, but the composition is why.
    "stainless": {"Fe": 0.690, "Cr": 0.180, "Ni": 0.100, "Mn": 0.020,
                  "Si": 0.010},
}

# Kept as a derived view so existing callers keep working: the target metal's
# own fraction, read out of the composition rather than stated twice.
METAL_FRACTION = {
    key: comp.get(METALS[key]["element"], 0.0) if key in METALS else 0.0
    for key, comp in COMPOSITION.items()
}

# Elements the arm has a capture route for. Everything else released by
# dissolution is unaccounted for, and saying so is the point.
CAPTURED_ELEMENTS = frozenset({"Fe"})
ELEMENT_NOTES = {
    "Mn": "Alloying element, not a contaminant. Neurotoxic on chronic "
          "systemic exposure; no capture route here.",
    "Si": "Largely inert as released silicate at this scale.",
    "C": "Carbide and free carbon; stays as insoluble particulate rather "
         "than dissolving, which makes it a detached-debris question "
         "rather than a chemistry one.",
    "P": "Trace. Enters the phosphate pool.",
    "Cr": "Recognised contact allergen, and as Cr(III) not captured by "
          "deferoxamine. In stainless it is also the reason the route "
          "refuses the material.",
    "Ni": "Recognised contact allergen and the commonest metal sensitiser. "
          "No capture route in this arm.",
}


def capacity(material: str, mass_mg: float | None) -> dict[str, Any]:
    """How much capture the fragment demands, derived from mass alone."""
    key = resolve(material)
    if key is None or mass_mg is None or mass_mg <= 0:
        return {"computable": False,
                "why": "needs a recognised metal and a fragment mass"}
    # Honour the route, not just the iron content. This guard was absent
    # while METAL_FRACTION held only steel and iron, so a metal with no route
    # fell out through the missing-fraction branch by accident. Giving
    # stainless a composition removed that accident and this function started
    # answering for a material the chemistry had already refused.
    if METALS[key]["route"] == "none":
        return {"computable": False,
                "why": f"{METALS[key]['name']} has no dissolution route, so "
                       "there is nothing to capture. "
                       + METALS[key].get("no_enzyme_reason", "")}
    fraction = METAL_FRACTION.get(key)
    element = METALS[key]["element"]
    if not fraction or element != "Fe":
        return {
            "computable": False,
            "why": (
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
        "note": "The architecture has a precedent: a hydrogel whose own "
                "hydroxyl and carboxyl groups chelate the released ion has been "
                "used in vivo to regulate a zinc scaffold's corrosion and "
                "stabilise its ion release (PMID 41885000). Zinc rather than "
                "iron, and a scaffold rather than a fragment, but a chelating "
                "gel controlling a corroding metal is not hypothetical. What "
                "nobody has done is load ferritin into one against a fragment.",
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


# ---------------------------------------------------------------------------
# How long. The arm refused to say, and refusing was right while the only
# honest answer was "unmeasured". It is not the only one any more.
#
# Corrosion rate in a physiological environment is measured in the
# biodegradable-implant literature, in millimetres of penetration per year.
# What is unmeasured is what a chelator adds to it. So the time is computed as
# a function of the rate, and the published multiples bracket the range: gold
# galvanic couples gave 4x and 9x over pure iron, sandblasting gave a
# persistent increase. Those are the anchors, and they are multiples rather
# than absolute rates because that is what the abstracts state.
#
# The geometry is what makes this worth computing. A cube eroding from every
# face is consumed when penetration reaches half its edge, but volume goes as
# the cube of the dimension -- so removing 20% of the volume costs only 3.6% of
# the edge. Full consumption and partial debulking differ by a factor of
# fourteen in penetration, which is the difference between decades and months.
# ---------------------------------------------------------------------------

# mm/year. Pure iron is bracketed because the abstracts say "too slow" without
# a figure; the accelerated values follow the multiples that were reported.
CORROSION_RATES_MM_PER_YEAR = {
    "pure_iron_low": 0.005,
    "pure_iron_high": 0.020,
    "accelerated_4x": 0.090,
    "accelerated_9x": 0.180,
}


def _penetration_fraction(volume_fraction: float) -> float:
    """Depth per face, as a fraction of edge length, to remove this volume."""
    if volume_fraction >= 1.0:
        return 0.5                      # faces meet at the centre
    return (1 - (1 - volume_fraction) ** (1 / 3)) / 2


def timeline(material: str, particle_size_mm: float | None,
             volume_fraction: float = 1.0) -> dict[str, Any]:
    """Years to remove this fraction of a fragment, across the rate range."""
    key = resolve(material)
    if key is None or METALS[key]["route"] == "none":
        return {"computable": False,
                "why": "no dissolution route for this metal: "
                       + METALS[key].get("no_enzyme_reason", "")}
    if not particle_size_mm or particle_size_mm <= 0:
        return {"computable": False, "why": "needs a particle size"}

    frac = _penetration_fraction(volume_fraction)
    depth_mm = particle_size_mm * frac
    rows = [
        {"label": label, "rate_mm_per_year": rate,
         "years": depth_mm / rate, "months": depth_mm / rate * 12}
        for label, rate in CORROSION_RATES_MM_PER_YEAR.items()
    ]
    return {
        "computable": True,
        "volume_fraction": volume_fraction,
        "penetration_fraction_of_edge": frac,
        "penetration_mm": depth_mm,
        "rows": rows,
        "basis": (
            "Penetration depth divided by corrosion rate. The depth is "
            "geometry; the rates are from the biodegradable-implant "
            "literature, where the accelerated values follow the 4x and 9x "
            "multiples reported for gold galvanic couples over pure iron."
        ),
        "what_is_unmeasured": (
            "What a chelator adds. Every rate here is for iron corroding on "
            "its own, because nobody has measured chelation against metallic "
            "iron. The chelator is expected to raise the rate by keeping the "
            "oxide from accumulating, and that expectation is the gap."
        ),
        "caveat": (
            "Penetration is linear in time only if the rate holds. An "
            "accumulating oxide slows it, which is the reason the chelator is "
            "in the design at all -- so a constant rate is the optimistic "
            "reading of these numbers, not the cautious one."
        ),
    }


def feasibility_by_goal(material: str, particle_size_mm: float | None) -> dict[str, Any]:
    """The conclusion the timeline forces, stated rather than left to inference.

    Full dissolution of anything but dust takes decades at every rate yet
    demonstrated. Debulking the same fragment takes months. Those are not two
    shades of the same answer, and the arm would be misleading if it reported
    the timeline without saying which goals survive it.
    """
    full = timeline(material, particle_size_mm, 1.0)
    part = timeline(material, particle_size_mm, 0.20)
    if not full.get("computable"):
        return full

    def at(result, label):
        return next(r["years"] for r in result["rows"] if r["label"] == label)

    full_years = at(full, "accelerated_4x")
    part_months = at(part, "accelerated_4x") * 12
    return {
        "computable": True,
        "full": {"years_at_demonstrated_rate": full_years,
                 "verdict": "not a clinical timescale" if full_years > 2
                            else "within reach"},
        "debulk_20pct": {"months_at_demonstrated_rate": part_months,
                         "verdict": "clinically plausible" if part_months <= 18
                                    else "slow but finite"},
        "why_they_differ": (
            "Volume goes as the cube of the dimension, so removing a fifth of "
            "it costs 3.6% of the edge where consuming all of it costs 50%. A "
            "factor of fourteen in penetration is the difference between "
            "decades and months."
        ),
        "conclusion": (
            "Dissolving a fragment away is not the product. Taking enough off "
            "to relieve a nerve, and clearing fragments small enough that the "
            "geometry is already favourable, are -- and those were the two "
            "goals this engine was asked about before the metal arm existed."
        ),
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
        # A refusal carries its consequences too, where they exist. For
        # stainless the chemistry is the easy half: the hard half is that a
        # radiograph does not distinguish it from carbon steel.
        for key_in, key_out in (("why_this_matters_clinically",
                                 "clinical_consequence"),
                                ("how_to_tell", "how_to_tell")):
            if m.get(key_in):
                out[key_out] = m[key_in]
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
            "refs": [REFS["ligand_dissolution"]],
            # Not a reference: PubMed returns nothing for a chelator against
            # metallic iron. A negative result has no DOI, and dressing it as
            # a citation produced two dead links.
            "searched_and_found_nothing": (
                "PubMed returns no results for chelator-driven dissolution of "
                "metallic iron. The oxide case is well studied and the metal "
                "case is not, which is the honest boundary of this route."
            ),
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
    if m["element"] == "Fe":
        out["unrusted_metal"] = {
            "question": "Everything here acts on the oxide. What about metal "
                        "that has not rusted?",
            "answer": (
                "There is none to treat. A fragment begins corroding the moment "
                "it enters tissue, so its surface is oxide by the time anyone "
                "sees it -- the measured case is the real one."
            ),
            "cycle": (
                "What happens underneath is the part that matters. Iron's oxide "
                "is a poor passivating layer -- porous and non-adherent where "
                "aluminium's and titanium's are dense and self-healing -- so "
                "strip it and fresh metal is exposed, "
                "oxygenated tissue re-oxidises that, and the chelator takes the "
                "new layer. The metal is consumed one layer at a time, "
                "indirectly, and the chelator never has to touch the lattice. "
                "Aluminium and titanium are excluded from this arm for exactly "
                "the reason this works for iron."
            ),
            "the_real_bottleneck": (
                "Which makes re-oxidation the rate-limiting step, not "
                "dissolution -- and that inverts this arm's own warning. The "
                "biodegradable-implant literature is explicit that iron "
                "corrodes too slowly in the body for its intended purpose. The "
                "safety concern about runaway release stands, but the "
                "engineering problem is the opposite one: making the fragment "
                "corrode at all."
            ),
            "but_not_nothing": (
                "Poor is not absent, and the team's clinical review is right "
                "to press on this: oxidising Fe(II) to Fe(III) produces oxides "
                "and hydroxides that do accumulate and do slow the reaction, "
                "so a ferroxidase on its own is not obviously an accelerant. "
                "That is the argument for a chelator setting the rate rather "
                "than an oxidase, and this arm reaches the same conclusion "
                "from the dissolution side."
            ),
            "what_moves_it": (
                "Surface state rather than chemistry. Sandblasting raised pure "
                "iron's corrosion rate and the increase held through long-term "
                "immersion. That lever is not available on an embedded "
                "fragment, but it says where to look: roughness and exposed "
                "area, not a stronger reagent."
            ),
            "evidence": LITERATURE,
            "refs": [REFS["iron_corrodes_too_slowly"], REFS["chelating_hydrogel"]],
        }
    if m["element"] == "Fe":
        out["direct_attack"] = _direct_fe0_attack(mass_mg=None)
    out["alternative"] = {
        "what": "Microbially influenced corrosion acts on metallic iron "
                "directly, by extracellular electron transfer from Fe(0).",
        "why_not_used": "As a community of living cells it is not a therapy: "
                        "deliberately establishing a biofilm in a wound is not "
                        "something to propose. But the enzymes behind it are a "
                        "different matter, and this arm was wrong about that "
                        "-- see the direct-attack section above.",
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


# ---------------------------------------------------------------------------
# The chelator ceiling, and the carrier's working life.
#
# Both of these come from a teammate's hydrogel architecture document, which
# specified the carrier this arm had only described as a requirement: a
# CMCS/OHA Schiff-base backbone, a thermo-contracting anti-swelling component,
# DFO grafted to chitosan as the chelator, and an enzyme depot. That document
# is the carrier, and it is better grounded clinically than the ferritin route
# above, because DFO is an approved drug with a renal clearance pathway and
# ferritin is a cytosolic protein nobody has injected.
#
# What it does not do is put two of its own numbers next to each other, and
# both are arithmetic:
#
# 1. Deferoxamine is a hexadentate siderophore. It binds Fe(III) one ion per
#    molecule, so the iron a depot can remove is capped by the DFO it carries,
#    whatever the enzyme does. At 560.68 g/mol against iron's 55.845 that is
#    ten milligrams of DFO per milligram of iron -- the chelator outweighs its
#    cargo tenfold. Nothing in the arm raises that; it is stoichiometry.
#
# 2. That same chelator is the accelerant. Dissolution rate tracks the
#    stability constant of the Fe(III)-ligand complex (PMID 25965980), so the
#    molecule driving the reaction is the molecule consumed by it. The capture
#    cannot fall behind the release -- which bounds the Fenton hazard by
#    construction, and is the strongest safety argument this arm has -- but it
#    also means the depot slows as it works.
#
# So a carrier that degrades in six to eight weeks is not a delivery detail.
# It is a dose interval, and the number of doses is the fragment's timeline
# divided by it.
# ---------------------------------------------------------------------------

DFO_FREE_BASE_G_PER_MOL = 560.68
DFO_MESYLATE_G_PER_MOL = 656.79
DFO_FE_STOICHIOMETRY = 1  # hexadentate: one Fe(III) per molecule


def chelator_demand(material: str, mass_mg: float | None,
                    volume_fraction: float = 1.0) -> dict[str, Any]:
    """How much deferoxamine the stated removal needs, by mass balance.

    Separate from capacity() above, which counts ferritin shells. This counts
    chelator molecules, because the carrier document builds on DFO and the two
    answer different questions: capacity() asks what stores the iron,
    chelator_demand() asks what can dissolve it in the first place.
    """
    key = resolve(material)
    if key is None or mass_mg is None or mass_mg <= 0:
        return {"computable": False,
                "why": "Needs a known metal and a fragment mass."}
    m = METALS[key]
    if m["element"] != "Fe":
        return {"computable": False,
                "why": f"DFO is selective for Fe(III); {m['name']} is not iron. "
                       "A chelator for this metal has not been chosen."}
    if m["route"] == "none":
        # Iron content is not the question. Stainless is iron and the chelator
        # still does nothing, because what stands in the way is a chromium
        # oxide film DFO does not lift. Computing a DFO mass here would be
        # arithmetic answering a question the chemistry has already closed.
        return {"computable": False,
                "why": f"{m['name']} has no dissolution route, so there is "
                       "nothing for a chelator to capture. "
                       + m.get("no_enzyme_reason", "")}

    fe_mg = mass_mg * METAL_FRACTION.get(key, 1.0) * volume_fraction
    free_base = fe_mg * DFO_FREE_BASE_G_PER_MOL / FE_G_PER_MOL
    mesylate = fe_mg * DFO_MESYLATE_G_PER_MOL / FE_G_PER_MOL
    return {
        "computable": True,
        "volume_fraction": volume_fraction,
        "iron_mg": fe_mg,
        "dfo_free_base_mg": free_base,
        "dfo_mesylate_mg": mesylate,
        "mg_dfo_per_mg_iron": DFO_FREE_BASE_G_PER_MOL / FE_G_PER_MOL,
        "basis": "Deferoxamine binds Fe(III) 1:1 as a hexadentate ligand, so "
                 "the demand is the iron's moles times the chelator's molar "
                 "mass. Arithmetic, not an estimate.",
        "what_this_bounds": (
            "The total iron one depot can remove, not the rate. A depot "
            "carrying less DFO than this cannot reach the stated removal no "
            "matter how good the enzyme is, because the chelator is consumed "
            "stoichiometrically as it works."
        ),
        "why_it_is_also_the_accelerant": (
            "The same molecule drives the dissolution it captures: the rate "
            "coefficient tracks the Fe(III)-ligand stability constant. Capture "
            "therefore cannot lag behind release, which bounds the Fenton "
            "hazard by construction -- and is the reason to prefer this to a "
            "faster route with separate capture."
        ),
        "evidence": DERIVED,
        "ref": REFS["ligand_dissolution"],
    }


# Weeks. The carrier document states six to eight for the Schiff-base network,
# and two to eight for nanochelator release. Eight is the generous reading of
# its own figure, so it is the one used: an optimistic denominator makes the
# placement count a lower bound.
CARRIER_LIFETIME_WEEKS = 8.0
_WEEKS_PER_MONTH = 365.25 / 7 / 12


def carrier_placements(material: str, particle_size_mm: float | None,
                       volume_fraction: float = 1.0,
                       carrier_weeks: float = CARRIER_LIFETIME_WEEKS,
                       ) -> dict[str, Any]:
    """How many sequential carrier placements the timeline implies.

    The question the architecture document leaves open. Its gel lives six to
    eight weeks; this arm's timeline says how long the metal takes. Dividing
    one by the other is the dosing schedule, and at most of the rate range it
    is not one injection.
    """
    t = timeline(material, particle_size_mm, volume_fraction)
    if not t.get("computable"):
        return {"computable": False, "why": t.get("why", "No timeline.")}

    rows = []
    for r in t["rows"]:
        weeks = r["months"] * _WEEKS_PER_MONTH
        rows.append({
            "label": r["label"],
            "rate_mm_per_year": r["rate_mm_per_year"],
            "weeks": weeks,
            "placements": weeks / carrier_weeks,
        })
    # A rate that lands a few days past the carrier's life is one placement in
    # practice, not two, and reporting it as "needs repeat dosing" would be
    # arithmetic pretending to be a finding. So the margin is named rather
    # than rounded away.
    single = [r for r in rows if r["placements"] <= 1.0]
    marginal = [r for r in rows if 1.0 < r["placements"] <= 1.25]
    repeat = [r for r in rows if r["placements"] > 1.25]
    covered = single + marginal
    return {
        "computable": True,
        "carrier_lifetime_weeks": carrier_weeks,
        "volume_fraction": volume_fraction,
        "penetration_mm": t["penetration_mm"],
        "rows": rows,
        "single_dose_cases": [r["label"] for r in single],
        "marginal_cases": [r["label"] for r in marginal],
        "repeat_dose_cases": [r["label"] for r in repeat],
        "finding": (
            f"One placement covers the stated removal at {len(covered)} of the "
            f"{len(rows)} corrosion rates in the range"
            + (f", and only at the fastest ({', '.join(r['label'] for r in covered)})."
               if covered and len(covered) < len(rows) else ".")
            + (f" The other {len(repeat)} need between "
               f"{min(r['placements'] for r in repeat):.0f} and "
               f"{max(r['placements'] for r in repeat):.0f} sequential placements."
               if repeat else "")
        ),
        "why_it_matters": (
            "A carrier lifetime and a fragment timeline quoted in different "
            "sections of the same document look compatible until they are "
            "divided. Repeat placement next to a nerve is a different clinical "
            "proposition from one injection, and it is the proposition the "
            "numbers actually describe."
        ),
        "evidence": DERIVED,
    }


# ---------------------------------------------------------------------------
# Direct attack on metallic iron, and the two things that stand in its way.
#
# This arm said, in plain words, that the only mechanism acting on metallic
# iron was "a living biofilm, not a protein that can be injected". The team's
# clinical review brought two papers that say otherwise, and they say it
# clearly enough that the claim had to go:
#
#   Tsurumaru 2018 -- a [NiFe] hydrogenase encoded beside its own Tat
#   secretion machinery, reaching the outside of the cell and oxidising Fe(0)
#   on contact. Deleting the island removes the corroding activity.
#
#   Deutzmann 2015 -- the cells are not needed. Free enzymes shed into the
#   medium, sorbed to the metal, account for the observed rates; a strain with
#   every catabolic hydrogenase deleted still shows it.
#
# So a secreted protein acting on solid Fe(0) is not hypothetical. It is the
# best lead this arm has, and it was ruled out by an assumption rather than by
# evidence.
#
# Two problems follow immediately, and neither is in the review. The first is
# oxygen. The second is arithmetic, and it is the one nobody has written down:
# the reaction makes hydrogen gas, one mole per mole of iron, and a fragment
# sits in a closed fibrotic capsule.
# ---------------------------------------------------------------------------

GAS_CONSTANT_L_ATM = 0.0820573
BODY_TEMPERATURE_K = 310.15


def hydrogen_evolution(material: str = "steel", mass_mg: float | None = None,
                       volume_fraction: float = 1.0) -> dict[str, Any]:
    """How much H2 the hydrogenase route would release, as a volume.

    Fe(0) + 2 H+ -> Fe(2+) + H2 is one mole of hydrogen per mole of iron, so
    the volume follows from the fragment's mass and nothing else. It is the
    same mass balance the rest of this arm runs on, pointed at the product
    instead of the reactant.
    """
    key = resolve(material)
    if key is None or mass_mg is None or mass_mg <= 0:
        return {"computable": False,
                "why": "Needs a known metal and a fragment mass."}
    if METALS[key]["element"] != "Fe":
        return {"computable": False,
                "why": "This stoichiometry is specific to Fe(0) oxidation."}
    if METALS[key]["route"] == "none":
        return {"computable": False,
                "why": f"{METALS[key]['name']} is not dissolved by this route, "
                       "so no hydrogen is evolved from it."}

    fe_mg = mass_mg * METAL_FRACTION.get(key, 1.0) * volume_fraction
    mol = fe_mg / 1000.0 / FE_G_PER_MOL
    litres = mol * GAS_CONSTANT_L_ATM * BODY_TEMPERATURE_K
    return {
        "computable": True,
        "volume_fraction": volume_fraction,
        "iron_mg": fe_mg,
        "h2_mmol": mol * 1000,
        "h2_ml_at_37c": litres * 1000,
        "basis": "One mole of H2 per mole of Fe(0) oxidised, from "
                 "Fe(0) + 2 H+ -> Fe(2+) + H2, at 37 C and one atmosphere.",
        "why_it_matters": (
            "A 20% debulk of a 50 mg fragment is about 4.5 mL of hydrogen, "
            "released inside an avascular fibrotic capsule next to the nerve "
            "the treatment exists to protect. Gas in a closed tissue space "
            "raises pressure, which is the symptom being treated, and on "
            "imaging it looks like gas-forming infection. Neither the clinical "
            "review nor the carrier document states this, and it follows from "
            "the reaction they both cite."
        ),
        "what_would_settle_it": (
            "Whether hydrogen diffuses out faster than it is made. H2 is the "
            "smallest molecule there is and tissue is not sealed, so the "
            "steady-state volume may be far below the total -- but that is a "
            "measurement, not an assumption, and the total is what the mass "
            "balance fixes."
        ),
        "evidence": DERIVED,
    }


def _direct_fe0_attack(mass_mg: float | None = None) -> dict[str, Any]:
    """The enzymes that act on metallic iron, and what blocks each."""
    return {
        "what_changed": (
            "This arm previously stated that nothing but a living biofilm "
            "attacks metallic iron. That was wrong, and the correction comes "
            "from the team's clinical feasibility review rather than from "
            "here."
        ),
        "enzymes": [
            {
                "name": "Extracellular [NiFe] hydrogenase",
                "organism": "Methanococcus maripaludis OS7",
                "reaction": "Fe(0) + 2 H+ -> Fe(2+) + H2",
                "why_it_matters": "Secreted through Tat machinery encoded in "
                                  "the same island, so it contacts Fe(0) "
                                  "directly. A deletion mutant loses the "
                                  "activity, which ties the phenotype to this "
                                  "protein rather than to the community.",
                "evidence": LITERATURE,
                "ref": REFS["extracellular_hydrogenase"],
            },
            {
                "name": "Cell-free hydrogenase and formate dehydrogenase",
                "organism": "Methanococcus maripaludis MM901",
                "reaction": "Fe(0) + 2 H+ -> Fe(2+) + H2; and with CO2, "
                            "Fe(0) + CO2 + H+ -> Fe(2+) + formate",
                "why_it_matters": "Spent medium with no cells in it takes "
                                  "electrons from Fe(0) at rates sufficient to "
                                  "explain the whole phenotype. This is the "
                                  "result that makes the route an injectable "
                                  "protein rather than an ecology.",
                "evidence": LITERATURE,
                "ref": REFS["cell_free_electron_uptake"],
            },
            {
                "name": "[FeFe] hydrogenase",
                "organism": "Clostridium acetobutylicum",
                "reaction": "Fe(0) + 2 H+ -> Fe(2+) + H2",
                "why_it_matters": "Direct electron transfer between the metal "
                                  "surface and the enzyme, shown to accelerate "
                                  "mild-steel corrosion. Cited in the team's "
                                  "review from Corrosion Science 2016, which "
                                  "PubMed does not index, so it is named here "
                                  "without an identifier rather than given a "
                                  "link this project cannot verify.",
                "evidence": LITERATURE,
                "ref": None,
            },
        ],
        "blocking_problems": [
            {
                "problem": "Oxygen",
                "detail": "Both hydrogenase classes are oxygen-sensitive, "
                          "many of them irreversibly so within minutes, and "
                          "both source organisms are strict anaerobes -- one "
                          "is a methanogenic archaeon. Tissue is oxygenated. "
                          "This is the first thing to establish and the review "
                          "does not raise it.",
                "severity": "blocking until shown otherwise",
                "what_would_settle_it": "Residual activity of the purified "
                                        "enzyme after exposure to air at the "
                                        "dissolved-oxygen tension of "
                                        "subcutaneous tissue. If it is minutes, "
                                        "the route needs an O2-tolerant "
                                        "hydrogenase, and those exist in "
                                        "Ralstonia and Aquifex -- which turns "
                                        "this into a protein-engineering "
                                        "programme with a known starting "
                                        "point.",
            },
            {
                "problem": "The product is a gas",
                "detail": "One mole of H2 per mole of iron, inside a closed "
                          "capsule. See hydrogen_evolution() for the volume; "
                          "it is millilitres, not microlitres.",
                "severity": "needs a number before it needs a solution",
                "what_would_settle_it": "Whether diffusion out beats "
                                        "production. H2 is the smallest "
                                        "molecule there is, so it may never "
                                        "accumulate -- but the total is fixed "
                                        "by the mass balance and has to be "
                                        "compared against it.",
            },
            {
                "problem": "It releases Fe(II), the dangerous oxidation state",
                "detail": "The reaction's iron product is ferrous, which is "
                          "the Fenton reactant. So this route does not remove "
                          "the capture requirement, it sharpens it: capture "
                          "has to be in place before dissolution starts, not "
                          "alongside it.",
                "severity": "same constraint as the rest of the arm",
                "what_would_settle_it": "Nothing new -- it is the chelator "
                                        "ceiling already computed here.",
            },
        ],
        "why_this_is_still_the_best_lead": (
            "Every other candidate in this arm acts on Fe(II) that is already "
            "in solution, which means something else has to dissolve the "
            "fragment first and the enzyme only manages the ion. These three "
            "act on the solid. That is the one step the arm could not "
            "otherwise fill, and it is filled by proteins rather than by "
            "chemistry alone."
        ),
        "evidence": LITERATURE,
    }


# ---------------------------------------------------------------------------
# Approved products where an enzyme touches a person.
#
# From the team's clinical feasibility review, which assembled it from the FDA
# Purple Book and current labels. It belongs in the engine because it answers
# the question a judge asks first -- has anyone ever injected an enzyme into a
# person on purpose -- and because two entries answer a narrower question this
# arm needed and had no answer for: whether an injected *oxidoreductase* has
# precedent. ELITEK and KRYSTEXXA are recombinant urate oxidases given
# intravenously, which is the closest regulatory analogue a ferroxidase has.
#
# Route of administration is the column that matters. The product here is a
# local depot, so the precedents worth most are the local ones.
# ---------------------------------------------------------------------------

CLINICAL_PRECEDENTS: tuple[dict[str, Any], ...] = (
    {
        "product": "XIAFLEX",
        "enzyme_class": "peptidase",
        "enzyme": "Collagenase clostridium histolyticum (AUX-I/AUX-II)",
        "route": "Intralesional injection",
        "proves": "A bacterial enzyme injected locally to break down a solid "
                  "structure at the site. The closest human precedent the "
                  "concept has.",
        "but": "Its own label warns against injection into nerves, vessels or "
               "other collagen-containing structures -- which is this "
               "product's anatomy. See hostsafety.PROPOSED_REAGENTS.",
        "locality": "local",
    },
    {
        "product": "HYLENEX",
        "enzyme_class": "glycosidase",
        "enzyme": "Recombinant human hyaluronidase PH20",
        "route": "Subcutaneous / infiltration",
        "proves": "Local enzymatic hydrolysis of extracellular matrix with a "
                  "recombinant human enzyme.",
        "but": "It degrades hyaluronic acid, which is the carrier backbone in "
               "the team's hydrogel design. An HA gel in tissue meets host "
               "hyaluronidase whether or not anyone injects more.",
        "locality": "local",
    },
    {
        "product": "ELITEK",
        "enzyme_class": "oxidoreductase",
        "enzyme": "Rasburicase, recombinant urate oxidase",
        "route": "Intravenous infusion",
        "proves": "An injected OXIDOREDUCTASE, used to change a substrate's "
                  "oxidation state fast. This is the regulatory analogue a "
                  "ferroxidase arm needed and did not have.",
        "but": "Systemic, and its substrate is a dissolved metabolite rather "
               "than a solid.",
        "locality": "systemic",
    },
    {
        "product": "KRYSTEXXA",
        "enzyme_class": "oxidoreductase",
        "enzyme": "Pegloticase, PEGylated recombinant uricase",
        "route": "Intravenous infusion",
        "proves": "A PEGylated engineered oxidase dosed chronically in people. "
                  "Precedent for both the enzyme class and the PEG carrier.",
        "but": "Also the precedent for the anti-PEG problem: pegloticase's own "
               "immunogenicity is dominated by anti-PEG antibodies, which is "
               "the risk flagged against Pluronic F127 in the carrier review.",
        "locality": "systemic",
    },
    {
        "product": "ACTIVASE / Cathflo",
        "enzyme_class": "peptidase",
        "enzyme": "Alteplase, recombinant tPA",
        "route": "IV; Cathflo instilled locally into a blocked catheter",
        "proves": "Enzymatic dissolution of a solid network, and a licensed "
                  "product whose whole mode of use is instillation into a "
                  "small closed space.",
        "but": "Fibrin is a protein network, not a mineral or a metal.",
        "locality": "local",
    },
    {
        "product": "NEXOBRID",
        "enzyme_class": "peptidase",
        "enzyme": "Anacaulase-bcdb, bromelain-enriched proteases",
        "route": "Topical gel on the burn",
        "proves": "Controlled enzymatic debridement replacing mechanical "
                  "excision -- the argument this product makes about surgery, "
                  "already approved for a different tissue.",
        "but": "Topical on an open wound, where a retained fragment is closed "
               "and deep.",
        "locality": "local",
    },
    {
        "product": "PALYNZIQ",
        "enzyme_class": "lyase",
        "enzyme": "Pegvaliase, PEGylated phenylalanine ammonia lyase",
        "route": "Chronic subcutaneous injection",
        "proves": "A non-human, engineered, PEGylated enzyme dosed chronically "
                  "in people.",
        "but": "Carries a boxed warning for anaphylaxis, which is the honest "
               "price of a microbial enzyme in a human.",
        "locality": "systemic",
    },
    {
        "product": "PULMOZYME",
        "enzyme_class": "nuclease",
        "enzyme": "Dornase alfa, recombinant human DNase I",
        "route": "Inhaled",
        "proves": "Local delivery to a compartment with low systemic "
                  "exposure, which is the depot argument.",
        "but": "The airway clears itself; a fibrotic capsule does not.",
        "locality": "local",
    },
)


def clinical_precedent(kind: str = "all") -> list[dict[str, Any]]:
    """Approved products, optionally narrowed to the locally administered ones.

    `kind` of "local" is the set worth citing for a depot, because systemic
    precedent answers a question this product is not asking.
    """
    if kind == "all":
        return list(CLINICAL_PRECEDENTS)
    return [p for p in CLINICAL_PRECEDENTS if p["locality"] == kind]


# ---------------------------------------------------------------------------
# Closing four gaps from f2c/gaps.py. Each follows the shape the rest of this
# module uses: returns `computable`, refuses with a `why` rather than guessing,
# and honours route() -- a metal with no dissolution route gets no quantities,
# because arithmetic answering a question the chemistry has closed is the
# failure this engine exists to refuse.
# ---------------------------------------------------------------------------

def _refuse(key: str | None, mass_mg: float | None, needs_mass: bool = True
            ) -> dict[str, Any] | None:
    """The guard every quantity function shares."""
    if key is None:
        return {"computable": False, "why": "unrecognised metal"}
    m = METALS[key]
    if m["route"] == "none":
        return {"computable": False,
                "why": f"{m['name']} has no dissolution route. "
                       + m.get("no_enzyme_reason", "")}
    if needs_mass and (mass_mg is None or mass_mg <= 0):
        return {"computable": False, "why": "needs a fragment mass"}
    return None


def released_elements(material: str, mass_mg: float | None,
                      volume_fraction: float = 1.0) -> dict[str, Any]:
    """Every element dissolution releases, not only the one with a route.

    Closes the `alloy` gap. The arm computed iron and ignored the rest of the
    fragment; the rest of the fragment is where the allergens are.
    """
    key = resolve(material)
    refusal = _refuse(key, mass_mg)
    if refusal:
        return refusal
    comp = COMPOSITION.get(key)
    if not comp:
        return {"computable": False,
                "why": f"No composition recorded for {METALS[key]['name']}. "
                       "A jacketed fragment's copper fraction depends on the "
                       "round, and guessing it would be the one invented "
                       "number in this arm."}

    dissolved = mass_mg * volume_fraction
    rows = []
    for element, fraction in sorted(comp.items(), key=lambda kv: -kv[1]):
        mg = dissolved * fraction
        rows.append({
            "element": element,
            "fraction": fraction,
            "mg_released": mg,
            "captured": element in CAPTURED_ELEMENTS,
            "note": ELEMENT_NOTES.get(element, ""),
        })
    uncaptured = [r for r in rows if not r["captured"] and r["mg_released"] > 0]
    return {
        "computable": True,
        "volume_fraction": volume_fraction,
        "dissolved_mg": dissolved,
        "elements": rows,
        "uncaptured_mg": sum(r["mg_released"] for r in uncaptured),
        "uncaptured_elements": [r["element"] for r in uncaptured],
        "finding": (
            f"{sum(r['mg_released'] for r in uncaptured):.2f} mg of the "
            f"{dissolved:.1f} mg dissolved is not iron and has no capture "
            f"route: {', '.join(r['element'] for r in uncaptured)}."
            if uncaptured else
            "Everything released is iron, which the chelator captures."
        ),
        "basis": "Nominal composition for the grade, multiplied by the mass "
                 "dissolved. The composition is not a measurement of any "
                 "particular fragment.",
        "what_is_assumed": (
            "The grade. Stage 1 of the protocol replaces this with XRF or "
            "SEM-EDS on the real fragment, and until it does, every "
            "non-iron figure here is a nominal value and not a finding."
        ),
        "evidence": DERIVED,
        "ref": REFS["fragment_chemistry"],
    }


def readout(material: str, mass_mg: float | None, volume_fraction: float = 1.0,
            over_weeks: float = 8.0) -> dict[str, Any]:
    """How anyone would know, in a living subject, that it is working.

    Closes the `readout` gap. The answer is not to watch the fragment: a 20%
    debulk is a 3.6% change in edge length, which routine imaging cannot see.
    It is to watch what comes out.

    Two facts settle which assay. Human iron excretion is inefficient and not
    regulated -- the body controls iron by absorption, not disposal (PMID
    38489995) -- so there is no physiological flux of iron into urine for a
    signal to hide behind. And deferoxamine's own route of clearance is
    urinary excretion of the chelated iron (PMID 15720959). The chelator the
    product already contains is therefore also its reporter.
    """
    key = resolve(material)
    refusal = _refuse(key, mass_mg)
    if refusal:
        return refusal
    if METALS[key]["element"] != "Fe":
        return {"computable": False,
                "why": "This readout is specific to iron: it rests on there "
                       "being no regulated excretion route for it."}
    if over_weeks <= 0:
        return {"computable": False, "why": "needs a time over which to spread"}

    fe_mg = mass_mg * METAL_FRACTION.get(key, 1.0) * volume_fraction
    days = over_weeks * 7.0
    per_day = fe_mg / days
    return {
        "computable": True,
        "volume_fraction": volume_fraction,
        "over_weeks": over_weeks,
        "iron_mg_total": fe_mg,
        "iron_mg_per_day": per_day,
        "recommended": "urinary ferrioxamine",
        "why_that_one": (
            "Ferrioxamine is not a normal constituent of urine, and humans "
            "have no regulated route that puts iron there, so the background "
            "it has to exceed is physiologically near-silent rather than "
            "merely low."
        ),
        "why_not_serum_iron": (
            "Serum iron is homeostatically buffered and is replenished "
            "continuously from senescent red cells, so a slow release is "
            "absorbed into a much larger managed flux. Watching it would be "
            "watching the regulator, not the fragment."
        ),
        "why_not_imaging": (
            "The quantity that changes is the one hardest to see. Removing "
            "20% of the volume shortens the edge by 3.6%, which is below what "
            "routine radiography resolves on a millimetre-scale fragment."
        ),
        "what_is_still_needed": (
            "A baseline. This project has not sourced a quantitative figure "
            "for urinary iron in an untreated person, so the signal-to-"
            "background ratio is argued mechanistically here and not "
            "computed. That number has to come from a reference before any "
            "detection claim is made."
        ),
        "basis": "Released iron divided by the time it is released over. The "
                 "total is fixed by the fragment's mass.",
        "evidence": DERIVED,
        "refs": [REFS["iron_homeostasis"], REFS["chelation_urinary"]],
    }


def enzyme_dose(material: str, mass_mg: float | None,
                rate_ug_per_cm2_per_day: float | None,
                surface_area_cm2: float | None = None,
                volume_fraction: float = 1.0,
                specific_activity_u_per_mg: float | None = None,
                ) -> dict[str, Any]:
    """How much enzyme the depot needs -- as arithmetic, not as a number.

    Closes the `enzyme_dose` gap in the only way it can honestly be closed.
    The rate has no default and the function refuses without it, because the
    rate is exactly what nobody has measured. What this does is make the gap
    one measurement wide instead of open-ended: stage 2 of the protocol
    produces the rate, and the dose then follows the way the chelator mass
    already does.
    """
    key = resolve(material)
    refusal = _refuse(key, mass_mg)
    if refusal:
        return refusal
    if rate_ug_per_cm2_per_day is None:
        return {
            "computable": False,
            "why": "No rate. This is the gap, not an oversight: no turnover "
                   "has been measured on a solid fragment at body "
                   "conditions, in either arm of this product.",
            "what_would_close_it": (
                "Stage 2 of the protocol measures dissolution per unit "
                "surface area on steel coupons at 37 C and pH 7.4. Pass that "
                "number as rate_ug_per_cm2_per_day and this returns a dose."
            ),
            "evidence": ABSENT,
        }
    if rate_ug_per_cm2_per_day <= 0:
        return {"computable": False,
                "why": "a non-positive rate removes the fragment never"}

    fe_mg = mass_mg * METAL_FRACTION.get(key, 1.0) * volume_fraction
    area = surface_area_cm2
    if area is None:
        # A sphere of the fragment's mass, as the conservative default: it is
        # the lowest surface area any shape of that mass can have, so the dose
        # it implies is the largest.
        density = 7.87  # g/cm3, iron
        volume_cm3 = (mass_mg / 1000.0) / density
        radius = (3 * volume_cm3 / (4 * math.pi)) ** (1 / 3)
        area = 4 * math.pi * radius ** 2
    days = (fe_mg * 1000.0) / (rate_ug_per_cm2_per_day * area)
    out = {
        "computable": True,
        "iron_mg": fe_mg,
        "surface_area_cm2": area,
        "surface_area_assumed": surface_area_cm2 is None,
        "rate_ug_per_cm2_per_day": rate_ug_per_cm2_per_day,
        "days_to_target": days,
        "weeks_to_target": days / 7.0,
        "basis": "Iron to remove, divided by rate times area. The area "
                 "defaults to a sphere of the same mass, which is the "
                 "smallest any shape can have and so the slowest case.",
        "evidence": DERIVED,
    }
    if specific_activity_u_per_mg:
        out["note_on_protein_mass"] = (
            "Converting a surface rate into milligrams of enzyme needs the "
            "turnover per unit of enzyme at the surface, which is a different "
            "measurement from specific activity in solution. Specific "
            "activity is recorded here but deliberately not multiplied "
            "through: that step is where a solution constant would be "
            "smuggled into a surface problem."
        )
        out["specific_activity_u_per_mg"] = specific_activity_u_per_mg
    return out


def aggregate(fragments: list[tuple[str, float, float]],
              volume_fraction: float = 1.0,
              carrier_weeks: float = CARRIER_LIFETIME_WEEKS) -> dict[str, Any]:
    """Sum the demands across every fragment a patient actually has.

    Closes the `multiple_fragments` gap. Each quantity in this arm was
    computed for one fragment; a blast patient has several, sometimes of more
    than one material. Two of the quantities do not scale comfortably -- the
    chelator ceiling and the hydrogen volume -- and that is the finding.

    `fragments` is a list of (material, mass_mg, size_mm).
    """
    if not fragments:
        return {"computable": False, "why": "no fragments given"}

    treatable, refused = [], []
    ferritin_mg = dfo_mg = h2_ml = iron_mg = 0.0
    placements = 0.0
    for material, mass_mg, size_mm in fragments:
        key = resolve(material)
        entry = {"material": material, "resolved": key,
                 "mass_mg": mass_mg, "size_mm": size_mm}
        if key is None or METALS[key]["route"] == "none":
            entry["why_refused"] = (
                _refuse(key, mass_mg) or {}).get("why", "no route")
            refused.append(entry)
            continue
        cap = capacity(key, mass_mg)
        chel = chelator_demand(key, mass_mg, volume_fraction)
        h2 = hydrogen_evolution(key, mass_mg, volume_fraction)
        place = carrier_placements(key, size_mm, volume_fraction, carrier_weeks)
        if cap.get("computable"):
            ferritin_mg += cap["ferritin_mg"]
        if chel.get("computable"):
            dfo_mg += chel["dfo_free_base_mg"]
            iron_mg += chel["iron_mg"]
        if h2.get("computable"):
            h2_ml += h2["h2_ml_at_37c"]
        if place.get("computable"):
            # The slowest rate in the bracket, because a course finishes when
            # its last fragment does.
            placements = max(placements,
                             max(r["placements"] for r in place["rows"]))
        entry["ferritin_mg"] = cap.get("ferritin_mg")
        entry["dfo_mg"] = chel.get("dfo_free_base_mg")
        entry["h2_ml"] = h2.get("h2_ml_at_37c")
        treatable.append(entry)

    return {
        "computable": True,
        "fragments": len(fragments),
        "treatable": treatable,
        "refused": refused,
        "volume_fraction": volume_fraction,
        "total_iron_mg": iron_mg,
        "total_ferritin_mg": ferritin_mg,
        "total_dfo_mg": dfo_mg,
        "total_h2_ml": h2_ml,
        "worst_case_placements": placements,
        "finding": (
            f"{len(treatable)} of {len(fragments)} fragments have a route. "
            f"Together they need {dfo_mg:.0f} mg of deferoxamine and would "
            f"release {h2_ml:.1f} mL of hydrogen."
            + (f" {len(refused)} fragment(s) have no route at all and are not "
               f"included in any of these totals." if refused else "")
        ),
        "why_it_matters": (
            "Treating five fragments is not five times a solved problem. The "
            "chelator demand is stoichiometric, so it adds up exactly, and a "
            "depot has a finite payload. The hydrogen adds up too, into the "
            "same tissue. Neither has a per-dose ceiling established, and "
            "that ceiling is what this total has to be compared against."
        ),
        "what_is_still_needed": (
            "The ceiling. A maximum tolerated local deferoxamine dose and a "
            "maximum tolerated gas volume are both unestablished, so this "
            "function reports the demand and cannot yet report whether it is "
            "acceptable."
        ),
        "evidence": DERIVED,
    }
