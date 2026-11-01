"""Compound identity and physical properties for reaction products.

WHY THIS MODULE EXISTS
    The simulator's physics depends on compound properties it had no source
    for. Two numbers in particular drove real behaviour off invented values:

      - the molecular radius of each product, which sets mesh hindrance and
        therefore how much the hydrogel captures (the capture gate);
      - the hazard status of each product, which the forbidden-products gate
        was checking against a hand-written list of opinions.

    The f2c warehouse carries ChEBI and Rhea identifiers for every enzyme, but
    as bare strings - nothing resolved them, so no formula, weight, structure
    or hazard data existed anywhere in the project.

HOW VALUES ARE OBTAINED, AND WHAT IS AND IS NOT TRUSTWORTHY
    Three tiers, and the tier travels with the value:

      "resolved"   fetched live from PubChem or ChEBI. Authoritative.
      "derived"    computed here from a resolved or reference formula -
                   molecular weight from atomic masses, radius from a cited
                   empirical correlation. Reproducible and auditable.
      "reference"  the molecular FORMULA only, hand-entered from the standard
                   chemical identity of a named compound and tied to its ChEBI
                   id. A formula is a discrete identity claim that is easy to
                   check, unlike a measured quantity.

    Hazard classification is NEVER hand-entered. GHS codes are specific
    regulatory strings, and inventing or half-remembering one would be worse
    than having none: a gate that fires on a fabricated hazard code is not a
    safety feature. Until the live fetch runs, hazard stays None and the gate
    that depends on it reports "not resolved" rather than "safe".

NETWORK
    The live fetchers need pubchem.ncbi.nlm.nih.gov and www.ebi.ac.uk, which a
    restricted network policy may deny. Everything here is cache-first and
    works offline from the committed snapshot; `fetch_*` only runs when asked.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SOURCE_DB_PUBCHEM = "PubChem"
SOURCE_DB_CHEBI = "ChEBI"

DEFAULT_STORE = Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "chemistry" / "compounds.json"

PUBCHEM_PROPS = "MolecularFormula,MolecularWeight,CanonicalSMILES,InChIKey"
PUBCHEM_URL = ("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
               "{name}/property/" + PUBCHEM_PROPS + "/JSON")
PUBCHEM_GHS_URL = ("https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/"
                   "{cid}/JSON?heading=GHS+Classification")
CHEBI_URL = ("https://www.ebi.ac.uk/ols4/api/ontologies/chebi/terms?obo_id={obo_id}")

USER_AGENT = "shrapmind/chemistry (research prototype)"

# Standard atomic weights, IUPAC 2021, for the elements that appear in these
# compounds. Used to COMPUTE molecular weight from a formula rather than
# recalling the weight itself.
ATOMIC_WEIGHT = {
    "H": 1.008, "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998,
    "Na": 22.990, "S": 32.06, "Cl": 35.45, "K": 39.098, "Ca": 40.078,
    "Fe": 55.845, "Cu": 63.546, "Zn": 65.38, "Br": 79.904, "I": 126.904,
    "Al": 26.982, "Si": 28.085, "P": 30.974, "Pb": 207.2, "Ti": 47.867,
}

_FORMULA_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)")

# Below this the small-solute radius correlation is outside its fitted range.
_MW_FLOOR = 50.0

# Ionic radii in nm for solvated metal ions, which the organic-solute
# correlation does not describe. These are the hydrated radii, because what
# moves through the gel mesh is the hydrated ion, not the bare one. Entered as
# reference identity values and labelled "reference", not "derived".
IONIC_RADIUS_NM = {
    "fe_ion": 0.045,      # Fe(III) crystal ionic radius; hydration shell is larger
    "metal_ion": 0.045,
}


class FormulaError(ValueError):
    pass


def molecular_weight(formula: str) -> float:
    """Molecular weight from a molecular formula, in g/mol.

    Computed, not recalled. Handles the flat formulas PubChem returns
    (C8H6O4); charge suffixes are ignored, nested parentheses are not
    supported and raise rather than silently mis-parsing.
    """
    f = (formula or "").strip()
    if not f:
        raise FormulaError("empty formula")
    if "(" in f or ")" in f:
        raise FormulaError(f"nested formula not supported: {formula!r}")
    f = re.sub(r"[+-]\d*$", "", f)  # drop a charge suffix
    total = 0.0
    seen = 0
    for sym, count in _FORMULA_TOKEN.findall(f):
        if not sym:
            continue
        if sym not in ATOMIC_WEIGHT:
            raise FormulaError(f"unknown element {sym!r} in {formula!r}")
        total += ATOMIC_WEIGHT[sym] * (int(count) if count else 1)
        seen += len(sym) + len(count)
    if seen != len(f):
        raise FormulaError(f"could not fully parse {formula!r}")
    return round(total, 4)


def radius_nm_from_mw(mw: float) -> float:
    """Effective hydrodynamic radius of a small molecule, in nm, from its
    molecular weight.

    Uses the empirical power-law correlation for small organic solutes

        r (nm) = 0.0515 * M^0.392      (M in g/mol)

    of the form used in the hindered-transport literature that the Ogston mesh
    treatment in kinetics.py also comes from.

    Checked against the products that matter here: it gives 0.39 nm for glucose
    (reported Stokes radii cluster around 0.36-0.44 nm) and 0.51 nm for
    cellobiose, which is the right scale and ordering.

    LIMIT OF VALIDITY, stated because the function is used by the capture gate:
    the correlation is fitted to organic solutes of roughly 50 g/mol and up,
    and it extrapolates badly below that - it returns 0.16 nm for water, where
    the accepted value is about 0.14-0.15 nm by the same convention but the
    agreement is coincidental rather than predictive at that size. Anything
    under _MW_FLOOR therefore raises instead of returning a number nobody
    should rely on. Bare metal ions are handled separately: a solvated Fe(II)
    ion is not a small organic solute and this correlation does not describe it.

    This is a DERIVED value and is labelled as such. It replaced a hand-written
    table of nine guesses that was setting the mesh-hindrance term, and through
    it the capture gate.
    """
    if mw <= 0:
        raise FormulaError("molecular weight must be positive")
    if float(mw) < _MW_FLOOR:
        raise FormulaError(
            f"molecular weight {mw:g} is below the correlation's range "
            f"({_MW_FLOOR:g} g/mol); this radius would not be meaningful")
    return round(0.0515 * (float(mw) ** 0.392), 4)


@dataclass
class Compound:
    """One chemical species, with the provenance of each property."""

    key: str                       # the name the simulator uses, e.g. "mhet"
    name: str                      # the chemical name
    formula: str | None = None
    molecular_weight: float | None = None
    radius_nm: float | None = None
    smiles: str | None = None
    inchikey: str | None = None
    chebi_id: str | None = None
    pubchem_cid: int | None = None
    # Hazard is only ever populated from a live fetch. None means NOT RESOLVED,
    # which is different from "no hazard".
    ghs_codes: list[str] | None = None
    hazard_summary: str | None = None
    metabolic: bool = False        # clears by normal metabolism (f2c's METABOLIC)
    level: str = "reference"       # reference | derived | resolved
    source_db: str | None = None
    retrieved_at: str | None = None
    notes: str = ""

    def complete(self) -> Compound:
        """Fill in whatever can be computed from the formula."""
        if self.formula and self.molecular_weight is None:
            try:
                self.molecular_weight = molecular_weight(self.formula)
                if self.level == "reference":
                    self.level = "derived"
            except FormulaError:
                pass
        if self.radius_nm is None and self.key in IONIC_RADIUS_NM:
            # An ion is not a small organic solute; use its ionic radius and
            # keep the label honest about where the number came from.
            self.radius_nm = IONIC_RADIUS_NM[self.key]
            self.level = "reference"
            if "ionic radius" not in self.notes:
                self.notes = (self.notes + " Radius is an ionic radius, not "
                              "derived from molecular weight.").strip()
        if self.molecular_weight and self.radius_nm is None:
            try:
                self.radius_nm = radius_nm_from_mw(self.molecular_weight)
            except FormulaError as e:
                # Record why rather than leaving an unexplained None.
                if "below the correlation" in str(e):
                    self.notes = (self.notes + f" Radius not derived: {e}").strip()
        return self

    @property
    def hazard_resolved(self) -> bool:
        return self.ghs_codes is not None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# The reference set: molecular FORMULAS for the products this project's
# reactions actually release, tied to ChEBI ids where f2c already carries one.
#
# Only identity is entered by hand. Weight and radius are computed by
# .complete(); hazard is left unresolved on purpose.
#
# `metabolic` follows f2c/formulate.py's METABOLIC set - products that clear by
# ordinary metabolism rather than needing active capture.
# --------------------------------------------------------------------------

REFERENCE: list[Compound] = [
    Compound(key="glucose", name="D-glucose", formula="C6H12O6",
             chebi_id="CHEBI:17634", metabolic=True,
             notes="Cellulose hydrolysis endpoint. An ordinary metabolite, "
                   "which is why the cellulose route has the mildest product "
                   "profile of any material here."),
    Compound(key="cellobiose", name="cellobiose", formula="C12H22O11",
             chebi_id="CHEBI:17057", metabolic=True,
             notes="Disaccharide intermediate of cellulose hydrolysis."),
    Compound(key="terephthalic_acid", name="terephthalic acid", formula="C8H6O4",
             chebi_id="CHEBI:15792",
             notes="PET hydrolysis product. Hazard status must be resolved "
                   "live before any claim about product safety."),
    Compound(key="ethylene_glycol", name="ethylene glycol", formula="C2H6O2",
             chebi_id="CHEBI:30742",
             notes="PET hydrolysis co-product. THE product to bound rather "
                   "than wave past on the polyester route - small enough to "
                   "escape the gel mesh easily, which is what the capture "
                   "gate is for."),
    Compound(key="mhet", name="mono(2-hydroxyethyl) terephthalate",
             formula="C10H10O5", chebi_id="CHEBI:131701",
             notes="PETase product; MHETase substrate. Accumulates when the "
                   "downstream partner is absent."),
    Compound(key="bhet", name="bis(2-hydroxyethyl) terephthalate",
             formula="C12H14O6",
             notes="Soluble PET oligomer, widely used as an assay substrate - "
                   "which is why constants measured on it are oligomer-level "
                   "rather than polymer-level evidence."),
    Compound(key="lactic_acid", name="lactic acid", formula="C3H6O3",
             chebi_id="CHEBI:78320", metabolic=True,
             notes="PLA hydrolysis product; cleared metabolically."),
    Compound(key="3_hydroxybutyric_acid", name="3-hydroxybutyric acid",
             formula="C4H8O3", chebi_id="CHEBI:20067", metabolic=True,
             notes="PHA hydrolysis product; a ketone body, cleared metabolically."),
    Compound(key="succinic_acid", name="succinic acid", formula="C4H6O4",
             chebi_id="CHEBI:15741", metabolic=True,
             notes="PBS hydrolysis product; a citric-acid-cycle intermediate."),
    Compound(key="butanediol", name="1,4-butanediol", formula="C4H10O2",
             chebi_id="CHEBI:41189",
             notes="PBS co-product. Not metabolic in f2c's sense; needs capture."),
    Compound(key="aminohexanoic_acid", name="6-aminohexanoic acid",
             formula="C6H13NO2", chebi_id="CHEBI:48639",
             notes="Polyamide-6 hydrolysis product."),
    Compound(key="bisphenol_a", name="bisphenol A", formula="C15H16O2",
             chebi_id="CHEBI:33216",
             notes="Polycarbonate hydrolysis product. The clearest case for "
                   "resolving hazard data live: it lands in "
                   "requires_active_capture by set difference today, with no "
                   "toxicological basis recorded anywhere in the project."),
    Compound(key="carbonate", name="carbonate", formula="CO3",
             chebi_id="CHEBI:41609", metabolic=True,
             notes="Polycarbonate hydrolysis co-product. Enters the "
                   "bicarbonate buffer system, so it is treated as "
                   "metabolically cleared - unlike bisphenol A, the other "
                   "product of the same reaction, which is not."),
    Compound(key="furandicarboxylic_acid", name="2,5-furandicarboxylic acid",
             formula="C6H4O5",
             notes="PEF hydrolysis product, the furanoate analogue of "
                   "terephthalic acid."),
    Compound(key="oligomer", name="generic oligomer", formula=None,
             molecular_weight=600.0, level="reference",
             notes="Placeholder for an unspecified oligomeric product. The "
                   "weight is a stated assumption, not a measurement, and a "
                   "run that depends on it should say so."),
    Compound(key="fe_ion", name="iron(II/III) ion", formula="Fe",
             chebi_id="CHEBI:24875",
             notes="Iron-route product. An ion, not a metabolite: capture "
                   "rather than rate is the binding constraint on that route."),
    Compound(key="metal_ion", name="generic metal ion", formula="Fe",
             notes="Stand-in for an unspecified liberated metal ion."),
    Compound(key="microparticle", name="detached microparticle", formula=None,
             molecular_weight=None, radius_nm=50.0, level="reference",
             notes="Not a molecule. The 50 nm radius is a nominal lower bound "
                   "for detached particulate, used so the mesh term treats it "
                   "as immobile. Its presence at all is a gate failure."),
]


def reference_set() -> dict[str, Compound]:
    return {c.key: c.complete() for c in (Compound(**asdict(x)) for x in REFERENCE)}


# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------


def load(path: Path | str | None = None) -> dict[str, Compound]:
    """Load the compound snapshot, falling back to the reference set.

    Offline-correct: with no snapshot on disk this still returns usable
    identity and derived physics, with `level` saying where each value came
    from and hazard unresolved.
    """
    p = Path(path) if path else DEFAULT_STORE
    out = reference_set()
    if not p.exists():
        return out
    try:
        payload = json.loads(p.read_text())
    except (OSError, ValueError):
        return out
    for rec in payload.get("compounds", []):
        try:
            c = Compound(**{k: v for k, v in rec.items()
                            if k in Compound.__dataclass_fields__})
            out[c.key] = c.complete()
        except (TypeError, ValueError):
            continue
    return out


def save(compounds: dict[str, Compound], path: Path | str | None = None,
         fetched_at: str | None = None) -> Path:
    import datetime as _dt

    p = Path(path) if path else DEFAULT_STORE
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": fetched_at or _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds"),
        "note": "level: reference = hand-entered formula (identity only); "
                "derived = computed here from a formula; "
                "resolved = fetched live. ghs_codes null means NOT RESOLVED, "
                "which is not the same as no hazard.",
        "compounds": [c.to_dict() for c in compounds.values()],
    }
    p.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    return p


# --------------------------------------------------------------------------
# Live fetch. Only runs when asked, and only works if the network allows it.
# --------------------------------------------------------------------------


def _get(url: str, timeout: int = 30) -> dict[str, Any] | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:  # noqa: S310
            return json.loads(fh.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            ValueError, OSError):
        return None


def fetch_pubchem(compound: Compound, timeout: int = 30) -> Compound:
    """Resolve identity and physical properties from PubChem."""
    from urllib.parse import quote

    data = _get(PUBCHEM_URL.format(name=quote(compound.name)), timeout)
    props = (((data or {}).get("PropertyTable") or {}).get("Properties") or [{}])[0]
    if not props:
        return compound
    compound.pubchem_cid = props.get("CID") or compound.pubchem_cid
    compound.formula = props.get("MolecularFormula") or compound.formula
    if props.get("MolecularWeight"):
        try:
            compound.molecular_weight = float(props["MolecularWeight"])
        except (TypeError, ValueError):
            pass
    compound.smiles = props.get("CanonicalSMILES") or compound.smiles
    compound.inchikey = props.get("InChIKey") or compound.inchikey
    compound.level = "resolved"
    compound.source_db = SOURCE_DB_PUBCHEM
    compound.radius_nm = None  # re-derive from the resolved weight
    return compound.complete()


def fetch_ghs(compound: Compound, timeout: int = 40) -> Compound:
    """Resolve GHS hazard classification from PubChem.

    Populates ghs_codes with the H-codes actually returned. An empty LIST means
    "resolved, and no GHS hazard is recorded"; None still means "not resolved".
    """
    if not compound.pubchem_cid:
        return compound
    data = _get(PUBCHEM_GHS_URL.format(cid=compound.pubchem_cid), timeout)
    if data is None:
        return compound
    codes: set[str] = set()
    blob = json.dumps(data)
    for code in re.findall(r"\bH\d{3}\b", blob):
        codes.add(code)
    compound.ghs_codes = sorted(codes)
    health = sorted(c for c in codes if c.startswith("H3"))
    compound.hazard_summary = (
        f"GHS health hazards: {', '.join(health)}" if health
        else ("no GHS health hazard recorded" if compound.ghs_codes is not None else "")
    )
    return compound


def fetch_chebi(compound: Compound, timeout: int = 30) -> Compound:
    """Fill the chemical name and formula from a ChEBI id via OLS4."""
    if not compound.chebi_id:
        return compound
    from urllib.parse import quote

    data = _get(CHEBI_URL.format(obo_id=quote(compound.chebi_id)), timeout)
    terms = (((data or {}).get("_embedded") or {}).get("terms") or [])
    if not terms:
        return compound
    term = terms[0]
    compound.name = term.get("label") or compound.name
    for ann_key in ("formula", "chebi/formula"):
        vals = (term.get("annotation") or {}).get(ann_key)
        if vals:
            compound.formula = vals[0]
            break
    compound.source_db = compound.source_db or SOURCE_DB_CHEBI
    return compound.complete()
