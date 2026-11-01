"""Will this enzyme, or what it releases, attack the patient?

`shared/safety.py` validates INPUTS and refuses clinical output. This module
is different: it encodes BIOLOGICAL hazard — whether a candidate catalyst has
activity against human tissue, and whether its reaction products carry a
documented mechanism of local harm.

WHY IT IS A SEPARATE CONCERN FROM THE TARGET CHEMISTRY
    The gate battery already asked "is the bond class we are attacking present
    in human tissue?" — a question about the *reaction specification*. That is
    not sufficient, and the knowledge base proves it: every one of the four
    peptidases in the warehouse is retrieved as a candidate for PLA. The PLA
    reaction spec is aliphatic-ester hydrolysis, which is not a human tissue
    bond, so a spec-level check passes them. But Proteinase K and the
    subtilisins are broad-spectrum serine proteases whose own catalytic
    activity is on PEPTIDE bonds — collagen, elastin, fibronectin, laminin,
    the structural proteins holding the wound together. Proteinase K's
    turnover number in this warehouse, 3509 s-1, was measured on casein: a
    protein.

    So the question has to be asked twice, about two different things:
      1. what reaction are we trying to run?            (reaction spec)
      2. what else can this particular protein do?      (this module)

WHAT THIS IS AND IS NOT
    It is a screen built on enzyme classification: EC number primarily, and
    enzyme-family names as a fallback because EC numbers in the warehouse are
    often partial (`3.4.-.-`) or absent. It flags a candidate whose CLASS acts
    on a host substrate.

    It is NOT a toxicology assessment, and class membership is not proof of
    harm in situ — a tethered enzyme inside a hydrogel is not the same
    exposure as free enzyme in tissue. But the burden of proof runs the right
    way round: a protease proposed for injection next to a nerve should have
    to demonstrate it does not digest tissue, not be assumed safe because
    nobody checked. Every flag names the host substrate at risk and the
    evidence tier, so a reviewer can disagree with a specific claim.

    Product hazard classifications (GHS) are fetched, never hand-entered —
    see f2c/sources/chemistry.py. What IS encoded here for products is their
    documented MECHANISM of local harm, which is a different kind of claim
    from a regulatory classification and is marked with the tier it rests on.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["blocking", "serious", "caution", "note"]
Tier = Literal["established", "documented", "plausible"]


@dataclass
class HostRisk:
    """One way a candidate could act on the patient rather than the fragment."""

    kind: str                 # proteolysis | lipolysis | glycan | oxidative | ...
    host_substrate: str       # what in the body is at risk
    why: str
    severity: Severity
    tier: Tier
    basis: str                # the EC class or name token that triggered it

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "host_substrate": self.host_substrate,
                "why": self.why, "severity": self.severity, "tier": self.tier,
                "basis": self.basis}


# --------------------------------------------------------------------------
# Enzyme classes with activity on host tissue.
#
# Keyed by EC prefix, longest match wins. `severity` "blocking" means a
# candidate of this class may not be advanced for a local injection without
# direct evidence of tissue selectivity.
# --------------------------------------------------------------------------

EC_HOST_RISK: list[tuple[str, HostRisk]] = [
    ("3.4.24", HostRisk(
        kind="proteolysis", host_substrate="collagen (metalloproteinase target)",
        why="Metalloproteinases of this class cleave collagen directly. Collagen "
            "is the load-bearing protein of the capsule, the tendon and the "
            "perineurium; digesting it is the mechanism of the iatrogenic "
            "damage this project exists to avoid.",
        severity="blocking", tier="established", basis="EC 3.4.24")),
    ("3.4.21", HostRisk(
        kind="proteolysis", host_substrate="host structural and plasma proteins",
        why="Serine endopeptidases of this class (subtilisin, proteinase K) are "
            "broad-spectrum: they hydrolyse peptide bonds with little sequence "
            "preference, so collagen, elastin, fibronectin and fibrinogen are "
            "all substrates. A turnover number measured on casein is a direct "
            "demonstration of protein-degrading activity.",
        severity="blocking", tier="established", basis="EC 3.4.21")),
    ("3.4", HostRisk(
        kind="proteolysis", host_substrate="host proteins (peptide bonds)",
        why="Any peptidase acts on the bond type that human tissue protein is "
            "built from. Selectivity for a polymer over host protein has to be "
            "demonstrated, not assumed.",
        severity="blocking", tier="established", basis="EC 3.4")),
    ("3.1.1.4", HostRisk(
        kind="membrane", host_substrate="membrane phospholipids",
        why="Phospholipase A2 hydrolyses membrane phospholipids, causing direct "
            "cell lysis and releasing arachidonic acid, which drives local "
            "inflammation. Haemolysis is a documented consequence.",
        severity="blocking", tier="established", basis="EC 3.1.1.4")),
    ("3.1.1.3", HostRisk(
        kind="lipolysis", host_substrate="triacylglycerols (adipose, membranes)",
        why="Triacylglycerol lipases hydrolyse host fat. The fragments this "
            "project targets sit in or near subcutaneous tissue and muscle, "
            "where adipose is abundant; free fatty acid release is locally "
            "irritant and pro-inflammatory.",
        severity="serious", tier="established", basis="EC 3.1.1.3")),
    ("3.2.1.35", HostRisk(
        kind="glycan", host_substrate="hyaluronan (extracellular matrix)",
        why="Hyaluronidase degrades the hyaluronan of the extracellular matrix. "
            "It is used clinically as a SPREADING factor precisely because it "
            "breaks down the barrier that keeps an injected agent local - the "
            "opposite of what a contained depot requires.",
        severity="blocking", tier="established", basis="EC 3.2.1.35")),
    ("4.2.2", HostRisk(
        kind="glycan", host_substrate="glycosaminoglycans",
        why="Polysaccharide lyases of this class cleave glycosaminoglycans, "
            "which are structural components of the extracellular matrix.",
        severity="serious", tier="documented", basis="EC 4.2.2")),
    ("3.2.1", HostRisk(
        kind="glycan", host_substrate="host glycans and glycoproteins",
        why="Glycoside hydrolases may act on host glycosaminoglycans and the "
            "glycan component of glycoproteins. Specificity varies widely "
            "within the class, so this is a flag for checking rather than a "
            "finding of harm.",
        severity="caution", tier="plausible", basis="EC 3.2.1")),
    ("1.11.1", HostRisk(
        kind="oxidative", host_substrate="any oxidisable biomolecule",
        why="Peroxidases consume or generate hydrogen peroxide. In an inflamed "
            "wound, where peroxide is already present from the respiratory "
            "burst, added peroxide chemistry means oxidative damage to lipids, "
            "proteins and DNA in the surrounding tissue.",
        severity="serious", tier="established", basis="EC 1.11.1")),
    ("1.13", HostRisk(
        kind="oxidative", host_substrate="host lipids and proteins",
        why="Oxygenases of this class incorporate molecular oxygen and can "
            "generate reactive intermediates; local oxidative stress is the "
            "concern rather than a specific substrate.",
        severity="caution", tier="plausible", basis="EC 1.13")),
    ("1.14", HostRisk(
        kind="oxidative", host_substrate="host lipids and proteins",
        why="Monooxygenases generate reactive oxygen intermediates as part of "
            "their mechanism.",
        severity="caution", tier="plausible", basis="EC 1.14")),
    ("3.1.1", HostRisk(
        kind="esterase", host_substrate="host carboxyl esters",
        why="Carboxylesterases are the main class here and are moderately "
            "promiscuous: host lipid esters and ester-containing signalling "
            "molecules are possible substrates. Lower concern than a protease, "
            "but not zero, and worth bounding experimentally.",
        severity="caution", tier="plausible", basis="EC 3.1.1")),
]

# Name tokens, used when the EC number is partial or missing. Deliberately
# conservative: these match enzyme-family names, not arbitrary words.
NAME_HOST_RISK: list[tuple[str, HostRisk]] = [
    (r"\b(collagenase|gelatinase)\b", HostRisk(
        kind="proteolysis", host_substrate="collagen",
        why="Named as a collagenase. Collagen is host structural protein; this "
            "cannot be made fragment-selective.",
        severity="blocking", tier="established", basis="name")),
    (r"\b(elastase)\b", HostRisk(
        kind="proteolysis", host_substrate="elastin",
        why="Named as an elastase. Elastin gives vessel walls and skin their "
            "recoil; degrading it locally is not recoverable.",
        severity="blocking", tier="established", basis="name")),
    (r"\b(protease|proteinase|peptidase|subtilisin|trypsin|chymotrypsin|"
     r"papain|bromelain|keratinase|thermolysin|savinase|alcalase)\b", HostRisk(
        kind="proteolysis", host_substrate="host proteins (peptide bonds)",
        why="Named as a protease family member. Acts on the bond type human "
            "tissue protein is built from.",
        severity="blocking", tier="established", basis="name")),
    (r"\b(hyaluronidase)\b", HostRisk(
        kind="glycan", host_substrate="hyaluronan",
        why="Degrades extracellular-matrix hyaluronan and acts as a spreading "
            "factor, defeating containment.",
        severity="blocking", tier="established", basis="name")),
    (r"\b(phospholipase)\b", HostRisk(
        kind="membrane", host_substrate="membrane phospholipids",
        why="Hydrolyses membrane phospholipids; direct cytolytic potential.",
        severity="blocking", tier="established", basis="name")),
    (r"\b(lipase)\b", HostRisk(
        kind="lipolysis", host_substrate="triacylglycerols",
        why="Named as a lipase; host fat is a substrate.",
        severity="serious", tier="established", basis="name")),
    (r"\b(peroxidase|laccase)\b", HostRisk(
        kind="oxidative", host_substrate="oxidisable biomolecules",
        why="Oxidative mechanism; generates or consumes peroxide, driving local "
            "oxidative stress in an already inflamed site.",
        severity="serious", tier="established", basis="name")),
]

# --------------------------------------------------------------------------
# Source-organism flags.
#
# Not a biosafety-level table and not a claim that the enzyme is infectious -
# a recombinant protein is not its source organism. The concern is narrower and
# practical: a protein from an organism that commonly infects wounds is a
# protein the local immune system may already be primed against, which raises
# the immunogenicity question, and its production needs endotoxin control.
# --------------------------------------------------------------------------

ORGANISM_FLAGS: dict[str, str] = {
    "clostridium": "wound-associated anaerobe; several species are themselves "
                   "sources of clinical collagenase, so cross-reactivity and "
                   "prior sensitisation are both plausible",
    "pseudomonas aeruginosa": "common wound pathogen; patients may be primed "
                              "against its antigens",
    "staphylococcus aureus": "the commonest wound pathogen; prior exposure is "
                             "near-universal",
    "burkholderia": "opportunistic pathogen; endotoxin control needed in "
                    "production",
    "mycobacterium": "slow-growing pathogen genus; antigens are strongly "
                     "immunostimulatory",
    "acinetobacter": "opportunistic wound pathogen, notable in blast and "
                     "combat injury",
    "candida": "opportunistic fungal genus; fungal protein glycosylation is "
               "itself immunostimulatory",
    "fusarium": "opportunistic fungal genus; mycotoxin-producing species exist, "
                "so preparation purity matters",
    "vibrio": "wound-infecting genus in marine exposure",
    "aspergillus fumigatus": "airway and wound pathogen; highly immunogenic",
    "serratia": "opportunistic pathogen",
    "klebsiella": "opportunistic pathogen",
}


@dataclass
class EnzymeSafety:
    """The host-safety assessment of one candidate."""

    name: str
    ec_numbers: list[str] = field(default_factory=list)
    organism: str = ""
    risks: list[HostRisk] = field(default_factory=list)
    organism_notes: list[str] = field(default_factory=list)
    off_optimum_c: float | None = None

    @property
    def blocking(self) -> bool:
        return any(r.severity == "blocking" for r in self.risks)

    @property
    def worst(self) -> Severity:
        for level in ("blocking", "serious", "caution", "note"):
            if any(r.severity == level for r in self.risks):
                return level  # type: ignore[return-value]
        return "note"

    def summary(self) -> str:
        if not self.risks:
            return (f"{self.name}: no host-substrate activity flagged from its "
                    f"classification. Absence of a flag is not evidence of "
                    f"selectivity.")
        worst = [r for r in self.risks if r.severity == self.worst]
        return (f"{self.name}: {self.worst.upper()} - "
                + "; ".join(f"{r.kind} on {r.host_substrate}" for r in worst))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "ec_numbers": self.ec_numbers,
            "organism": self.organism,
            "blocking": self.blocking, "worst_severity": self.worst,
            "risks": [r.to_dict() for r in self.risks],
            "organism_notes": self.organism_notes,
            "off_optimum_c": self.off_optimum_c,
            "summary": self.summary(),
        }


def host_risks(ec_numbers: list[str] | None, name: str = "") -> list[HostRisk]:
    """Host-substrate risks implied by an enzyme's classification.

    EC first, longest prefix wins so 3.4.21 beats the generic 3.4. Name tokens
    are checked as well, because a partial EC like "3.4.-.-" still identifies a
    peptidase and a missing EC must not mean a missing flag.
    """
    found: list[HostRisk] = []
    seen: set[str] = set()

    for ec in ec_numbers or []:
        clean = str(ec).strip()
        for prefix, risk in EC_HOST_RISK:  # list is ordered most-specific-first
            if clean.startswith(prefix):
                if risk.kind not in seen:
                    found.append(risk)
                    seen.add(risk.kind)
                break

    low = (name or "").lower()
    for pattern, risk in NAME_HOST_RISK:
        if re.search(pattern, low):
            # A name hit can upgrade severity for a kind already flagged.
            existing = next((r for r in found if r.kind == risk.kind), None)
            if existing is None:
                found.append(risk)
                seen.add(risk.kind)
            elif _rank(risk.severity) > _rank(existing.severity):
                found[found.index(existing)] = risk
    return found


def _rank(sev: str) -> int:
    return {"blocking": 3, "serious": 2, "caution": 1, "note": 0}.get(sev, 0)


def organism_flags(organism: str | None) -> list[str]:
    """Flags implied by the source organism's name.

    Matched on WORD BOUNDARIES. A substring search gets this wrong in a way
    that is easy to miss and embarrassing to ship: "Candidatus Bathyarchaeota"
    contains the letters of "candida", but Candidatus is a taxonomic prefix
    meaning "candidate taxon" and has nothing to do with the fungus. Flagging
    an uncultured archaeon as a fungal pathogen would discredit every other
    flag this module raises.
    """
    o = (organism or "").lower()
    out: list[str] = []
    for genus, note in ORGANISM_FLAGS.items():
        # Each key may be one word ("candida") or two ("pseudomonas aeruginosa").
        if re.search(r"\b" + re.escape(genus) + r"\b", o):
            out.append(f"{genus}: {note}")
    return out


def assess_enzyme(name: str, ec_numbers: list[str] | None = None,
                  organism: str = "", t_opt_c: float | None = None,
                  body_temperature_c: float = 37.0) -> EnzymeSafety:
    """Screen one candidate for activity against the patient."""
    s = EnzymeSafety(
        name=name or "unnamed",
        ec_numbers=list(ec_numbers or []),
        organism=organism or "",
        risks=host_risks(ec_numbers, name),
        organism_notes=organism_flags(organism),
    )
    if t_opt_c is not None:
        s.off_optimum_c = round(float(t_opt_c) - body_temperature_c, 1)
    return s


# --------------------------------------------------------------------------
# PRODUCT-SIDE HAZARD: the documented MECHANISM by which a degradation
# product could harm the tissue around the fragment.
#
# This is a different kind of claim from a GHS classification and is kept
# separate from it on purpose. A GHS code is a regulatory determination that
# must be fetched from a registry and must never be hand-entered
# (f2c/sources/chemistry.py enforces that). A mechanism is a statement about
# chemistry or metabolism that can be reasoned about and checked against the
# literature, and it is what actually tells a reviewer WHY a product matters.
#
# Every entry carries its tier, and `requires` names the mitigation the
# formulation would have to demonstrate. None of this substitutes for
# toxicological assessment.
# --------------------------------------------------------------------------


@dataclass
class ProductHazard:
    """How one reaction product could do local or systemic harm."""

    product: str
    mechanism: str
    endpoint: str
    severity: Severity
    tier: Tier
    requires: str

    def to_dict(self) -> dict[str, Any]:
        return {"product": self.product, "mechanism": self.mechanism,
                "endpoint": self.endpoint, "severity": self.severity,
                "tier": self.tier, "requires": self.requires}


PRODUCT_HAZARD: dict[str, ProductHazard] = {
    "ethylene_glycol": ProductHazard(
        product="ethylene_glycol",
        mechanism="Oxidised in vivo by alcohol dehydrogenase to glycolaldehyde, "
                  "then glycolic acid, then oxalic acid. Oxalate precipitates "
                  "with calcium as insoluble crystals.",
        endpoint="Metabolic acidosis and calcium-oxalate nephropathy; "
                 "dose-dependent and systemic rather than local.",
        severity="serious", tier="established",
        requires="A bounded total release, not just a release rate. The "
                 "quantity is set by the fragment's mass through the mass "
                 "balance, so for a small fragment the absolute amount may be "
                 "far below any toxic threshold - but that has to be computed "
                 "and stated, not assumed. This is the single strongest reason "
                 "the polyester route needs its mass balance closed."),
    "butanediol": ProductHazard(
        product="butanediol",
        mechanism="1,4-butanediol is metabolised by alcohol and aldehyde "
                  "dehydrogenase to gamma-hydroxybutyrate (GHB).",
        endpoint="CNS depression; GHB is a controlled substance with recognised "
                 "sedative and anaesthetic effects.",
        severity="serious", tier="established",
        requires="Capture or a demonstrated release quantity far below a "
                 "pharmacologically active dose. Of all the products here this "
                 "is the one most likely to have a systemic effect at a small "
                 "absolute amount."),
    "bisphenol_a": ProductHazard(
        product="bisphenol_a",
        mechanism="Binds nuclear and membrane oestrogen receptors as an agonist "
                  "at low concentrations.",
        endpoint="Endocrine activity. The dose-response is contested and "
                 "non-monotonic in parts of the literature, which makes a "
                 "'safe local amount' argument hard to make convincingly.",
        severity="blocking", tier="established",
        requires="This product should not be generated inside tissue without "
                 "a specific regulatory and toxicological case. The "
                 "polycarbonate route is gated on it, not merely cautioned."),
    "aromatic_amine": ProductHazard(
        product="aromatic_amine",
        mechanism="Polyurethane hydrolysis can liberate aromatic diamines from "
                  "the hard segment; several, including 4,4'-"
                  "methylenedianiline and toluenediamines, are classified "
                  "human or probable human carcinogens.",
        endpoint="Genotoxic and carcinogenic potential.",
        severity="blocking", tier="established",
        requires="Demonstrated amine-free product panel. A polyurethane route "
                 "that cannot show this must not advance regardless of its "
                 "erosion rate - the product panel is the gate, not the "
                 "kinetics."),
    "fe_ion": ProductHazard(
        product="fe_ion",
        mechanism="Free Fe(II) reacts with hydrogen peroxide by Fenton "
                  "chemistry: Fe(II) + H2O2 -> Fe(III) + OH- + hydroxyl "
                  "radical. The hydroxyl radical is the most reactive oxygen "
                  "species in biology and reacts at diffusion-limited rates "
                  "with whatever it meets. A wound site is the worst possible "
                  "place for this, because activated neutrophils generate "
                  "peroxide there as part of the respiratory burst - the "
                  "co-reactant is already present and abundant.",
        endpoint="Lipid peroxidation, protein carbonylation and DNA strand "
                 "breaks in the tissue immediately around the fragment. Iron "
                 "overload is also a known driver of ferroptotic cell death.",
        severity="blocking", tier="established",
        requires="Chelation-grade capture, not merely 'capture'. The gel must "
                 "bind iron as it is liberated, in a form that keeps it "
                 "redox-inactive - a chelator that holds iron but leaves it "
                 "able to cycle between Fe(II) and Fe(III) does not solve this. "
                 "THIS IS WHY THE METAL ROUTE IS CONSTRAINED BY CAPTURE AND NOT "
                 "BY RATE: dissolving the fragment faster than the gel can "
                 "sequester the ions converts a locally inert object into "
                 "distributed oxidative injury, which is unambiguously worse "
                 "than leaving it in place."),
    "metal_ion": ProductHazard(
        product="metal_ion",
        mechanism="Liberated transition-metal ions may participate in redox "
                  "cycling and displace physiological metals from "
                  "metalloproteins.",
        endpoint="Local oxidative stress and enzyme inhibition.",
        severity="serious", tier="documented",
        requires="Speciation - which ion, in which oxidation state - and "
                 "capture capacity for it. 'Metal' is not a specification."),
    "terephthalic_acid": ProductHazard(
        product="terephthalic_acid",
        mechanism="A dicarboxylic acid of low acute systemic toxicity; the "
                  "local concern is pH and the possibility of precipitation at "
                  "high local concentration rather than a specific receptor or "
                  "metabolic interaction.",
        endpoint="Local acidification and potential crystal formation if "
                 "released faster than it is cleared.",
        severity="caution", tier="documented",
        requires="Local pH buffering, and a release rate the gel's capacity "
                 "can absorb."),
    "microparticle": ProductHazard(
        product="microparticle",
        mechanism="Particulate debris detached from the fragment surface is "
                  "phagocytosed, drives a foreign-body response, and - being "
                  "mobile - can migrate away from the treated site.",
        endpoint="Chronic granulomatous inflammation at multiple sites rather "
                 "than one, and loss of the containment the whole approach "
                 "depends on.",
        severity="blocking", tier="established",
        requires="Surface erosion rather than bulk fragmentation. This is why "
                 "the model is a shrinking-core surface model: a route that "
                 "breaks the fragment up has converted one locatable object "
                 "into many unlocatable ones, which is worse than the "
                 "untreated state."),
}

# Products that clear by ordinary metabolism. Mirrors f2c/formulate.METABOLIC
# and is the reason the cellulose and PHA routes have the mildest product
# profiles of anything considered here.
BENIGN_PRODUCTS: dict[str, str] = {
    "glucose": "Ordinary metabolite; enters glycolysis directly.",
    "cellobiose": "Hydrolysed to glucose by host and microbial "
                  "beta-glucosidases; the disaccharide itself is inert.",
    "lactic_acid": "Ordinary metabolite; cleared by the Cori cycle. Local "
                   "acidification is the only concern and is buffered.",
    "3_hydroxybutyric_acid": "A physiological ketone body.",
    "succinic_acid": "A citric-acid-cycle intermediate.",
    "carbonate": "Enters the bicarbonate buffer system.",
}


def product_hazards(products: list[str] | None) -> tuple[list[ProductHazard], list[str], list[str]]:
    """Classify a product panel.

    Returns (hazards, benign, unassessed). `unassessed` is the important one:
    a product with neither a hazard entry nor a benign entry has not been
    thought about, and that is reported rather than passed over.
    """
    hazards: list[ProductHazard] = []
    benign: list[str] = []
    unassessed: list[str] = []
    for p in products or []:
        key = str(p)
        if key in PRODUCT_HAZARD:
            hazards.append(PRODUCT_HAZARD[key])
        elif key in BENIGN_PRODUCTS:
            benign.append(key)
        else:
            unassessed.append(key)
    return hazards, benign, unassessed


def assess_products(products: list[str] | None) -> dict[str, Any]:
    """Product-panel assessment for the gate battery and the report."""
    hazards, benign, unassessed = product_hazards(products)
    blocking = [h for h in hazards if h.severity == "blocking"]
    return {
        "hazards": [h.to_dict() for h in hazards],
        "benign": [{"product": p, "why": BENIGN_PRODUCTS[p]} for p in benign],
        "unassessed": unassessed,
        "blocking": [h.product for h in blocking],
        "worst_severity": (
            "blocking" if blocking else
            "serious" if any(h.severity == "serious" for h in hazards) else
            "caution" if hazards else "note"),
        "summary": (
            f"{len(blocking)} product(s) with a blocking hazard mechanism: "
            f"{', '.join(h.product for h in blocking)}" if blocking else
            f"{len(hazards)} product(s) carry a documented hazard mechanism; "
            f"{len(benign)} clear metabolically"
            + (f"; {len(unassessed)} not assessed" if unassessed else "")),
    }
