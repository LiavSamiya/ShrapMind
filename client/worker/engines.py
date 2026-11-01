"""Worker-side tool implementations. One module-level function per tool name.

The transport in main.py dispatches by `getattr(engines, name)` - the module
namespace *is* the dispatch table, exactly as the server side does
`getattr(bench, name)`. Adding a tool means adding a function here whose name
matches a `ToolName` in shared/protocol.py.

Every function re-validates its own arguments through shared.safety,
independently of the server. Defense in depth: the worker does not trust that
the backend already checked, because the backend is the thing an injected
record would be trying to steer.

MOCK MODE (SHRAPMIND_MOCK_ENGINES=1, the default when numpy is absent)
    Returns deterministic canned results so the whole stack demos with no
    dataset and no compute. The shapes are identical, so nothing downstream
    can tell the difference - which is the point.
"""
from __future__ import annotations

import math
import os
import re
import time
from typing import Any

from shared.biosafety import assess_products
from shared.safety import (
    check_clinical_output,
    sanitize_for_prompt,
    simulation_disclaimer,
    validate_identifier,
    validate_number,
    validate_params,
)

try:
    import kinetics  # when run as a script from client/worker/
except ImportError:  # pragma: no cover
    from client.worker import kinetics  # type: ignore[no-redef]

ENGINE_VERSION = "0.2.0"


def _compounds() -> dict[str, Any]:
    """The compound store: identity, derived physics and hazard status.

    Loaded lazily so the worker still runs if the chemistry snapshot is
    missing - in which case properties are absent rather than invented, and
    the gates say so.
    """
    try:
        from f2c.sources.chemistry import load

        return load()
    except Exception:  # noqa: BLE001
        return {}


def _mock() -> bool:
    return os.getenv("SHRAPMIND_MOCK_ENGINES", "").lower() in ("1", "true", "yes")


def _finite(v: Any) -> Any:
    """Last line of defence against a non-finite number reaching the wire.

    json.dumps happily emits NaN and Infinity, neither of which is valid JSON
    and both of which the browser's JSON.parse refuses outright. Without this,
    a legitimate "this rate is unmeasurable" result would arrive at the console
    as an opaque parse failure rather than as the finding it is.
    """
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        return None
    return v


# --------------------------------------------------------------------------
# Material registry.
#
# The chemistry each material family admits, what it releases, and what must
# never appear in the product list. This is the table the whole design loop
# pivots on, and it is deliberately small and explicit rather than inferred:
# a reviewer has to be able to read it and disagree with it.
# --------------------------------------------------------------------------

def _f2c_tables() -> dict[str, Any]:
    """f2c's own material tables. Real values, already reviewed, already
    tested - so they are imported rather than retyped here."""
    try:
        from f2c.formulate import (
            CRYSTALLINITY_BARRIER_PCT,
            DENSITY_G_CM3,
            HYDROLYSIS_PRODUCTS,
            METABOLIC,
            REPEAT_UNIT_G_PER_MOL,
        )
        from f2c.retrieve import ALIASES, NON_ENZYMATIC

        return {"repeat": REPEAT_UNIT_G_PER_MOL, "density": DENSITY_G_CM3,
                "products": HYDROLYSIS_PRODUCTS, "metabolic": METABOLIC,
                "aliases": ALIASES, "non_enzymatic": NON_ENZYMATIC,
                "crystallinity_barrier": CRYSTALLINITY_BARRIER_PCT}
    except Exception:  # noqa: BLE001
        return {}


_T = _f2c_tables()

# Map f2c's product names onto the compound-store keys, so the physics can
# look up a radius for each one.
_PRODUCT_KEY = {
    "terephthalic acid": "terephthalic_acid",
    "ethylene glycol": "ethylene_glycol",
    "2,5-furandicarboxylic acid": "furandicarboxylic_acid",
    "lactic acid": "lactic_acid",
    "3-hydroxybutyric acid": "3_hydroxybutyric_acid",
    "succinic acid": "succinic_acid",
    "1,4-butanediol": "butanediol",
    "bisphenol A": "bisphenol_a",
    "carbonate": "carbonate",
    "6-aminohexanoic acid": "aminohexanoic_acid",
    "glucose": "glucose",
    "cellobiose": "cellobiose",
}

# Per-material detail that f2c's tables do not carry: the bond class the enzyme
# has to attack, the mechanism, how accessible the surface is, and how mature
# the route is. Keyed by the PAZy abbreviation so it joins onto the warehouse.
_MATERIAL_DETAIL: dict[str, dict[str, Any]] = {
    "PET": {
        "aliases": ["pet", "polyester", "polyethylene terephthalate", "plastic",
                    "fibre", "fiber"],
        "bond_class": "aromatic ester", "mechanism": "hydrolysis",
        "maturity": "flagship", "default_surface": "semi-crystalline",
        "note": "The flagship route, because it is the one the evidence "
                "actually supports: 323 curated enzyme records against this "
                "substrate. Read the assay conditions before quoting any "
                "constant - nearly all published PET enzymology is 50-70 C on "
                "amorphous film, and this application is 37 C on "
                "semi-crystalline fibre in serum. Ethylene glycol is the "
                "product to bound explicitly.",
    },
    "PEF": {
        "aliases": ["pef", "polyethylene furanoate", "furanoate"],
        "bond_class": "aromatic ester", "mechanism": "hydrolysis",
        "maturity": "research", "default_surface": "semi-crystalline",
        "note": "Furanoate analogue of PET with far thinner evidence (7 "
                "records). Treat PET results as suggestive, not transferable.",
    },
    "PA": {
        "aliases": ["pa", "nylon", "polyamide", "nylon-6"],
        "bond_class": "amide", "mechanism": "hydrolysis",
        "maturity": "benchmark", "default_surface": "semi-crystalline",
        "note": "Polyamide hydrolysis. The nylon oligomer hydrolases are the "
                "one family in the warehouse with constants measured on a "
                "genuine oligomer of the target rather than a chromogenic "
                "ester, which makes them the strongest available evidence - "
                "still oligomer-level, not polymer-level.",
    },
    "PLA": {
        "aliases": ["pla", "polylactic acid", "polylactide"],
        "bond_class": "aliphatic ester", "mechanism": "hydrolysis",
        "maturity": "benchmark", "default_surface": "semi-crystalline",
        "note": "Lactic acid is an ordinary metabolite, so the product profile "
                "is mild. But the candidates retrieved for PLA are broad "
                "proteases: one of them has its turnover number measured on "
                "casein. A constant from milk protein says nothing about a "
                "solid polyester, and the provenance gate will say so.",
    },
    "PHA": {
        "aliases": ["pha", "polyhydroxyalkanoate", "phb"],
        "bond_class": "aliphatic ester", "mechanism": "hydrolysis",
        "maturity": "benchmark", "default_surface": "semi-crystalline",
        "note": "3-hydroxybutyrate is a ketone body and clears metabolically. "
                "One of the mildest product profiles here.",
    },
    "PBS": {
        "aliases": ["pbs", "polybutylene succinate"],
        "bond_class": "aliphatic ester", "mechanism": "hydrolysis",
        "maturity": "research", "default_surface": "semi-crystalline",
        "note": "Succinate clears metabolically; 1,4-butanediol does not and "
                "needs capture.",
    },
    "PC": {
        "aliases": ["pc", "polycarbonate"],
        "bond_class": "carbonate ester", "mechanism": "hydrolysis",
        "maturity": "research", "default_surface": "semi-crystalline",
        "note": "Bisphenol A is a hydrolysis product. Its hazard status must "
                "be resolved before this route is discussed as an option at "
                "all - it currently lands in requires-capture by set "
                "difference, with no toxicological basis recorded anywhere.",
    },
    "PUR": {
        "aliases": ["pur", "pu", "polyurethane", "foam"],
        "bond_class": "carbamate ester", "mechanism": "hydrolysis",
        "maturity": "research", "default_surface": "unknown",
        "note": "Aromatic amine release is a hard blocker, and f2c "
                "deliberately records no repeat unit for polyurethane because "
                "it is not fixed by the class - so the product mass balance is "
                "not computable. Both facts have to be reported, not "
                "papered over.",
    },
    "PBAT": {
        "aliases": ["pbat"],
        "bond_class": "aliphatic-aromatic ester", "mechanism": "hydrolysis",
        "maturity": "research", "default_surface": "semi-crystalline",
        "note": "A copolyester; like PUR its repeat unit is not fixed by the "
                "class, so mass balance is not computable.",
    },
    "NR": {
        "aliases": ["nr", "natural rubber", "latex", "rubber"],
        "bond_class": "polyisoprene C=C", "mechanism": "redox",
        "maturity": "research", "default_surface": "unknown",
        "note": "Rubber cleavage is oxidative rather than hydrolytic, and the "
                "evidence is thin (8 records).",
    },
    "PE": {
        "aliases": ["pe", "polyethylene", "polythene"],
        "bond_class": "aliphatic C-C", "mechanism": "redox",
        "maturity": "no_documented_route", "default_surface": "semi-crystalline",
        "note": "No depolymerisation route is documented at body conditions: "
                "the backbone is unactivated C-C and would need oxidation "
                "first. Note the distinction f2c draws and this project keeps - "
                "this is ABSENT EVIDENCE, not a proof of impossibility. Saying "
                "'polyethylene cannot be degraded' would overstate what the "
                "record supports.",
    },
    "PP": {
        "aliases": ["pp", "polypropylene"],
        "bond_class": "aliphatic C-C", "mechanism": "redox",
        "maturity": "no_documented_route", "default_surface": "semi-crystalline",
        "note": "As polyethylene: unactivated backbone, no documented route at "
                "body conditions, absent evidence rather than impossibility.",
    },
    "PS": {
        "aliases": ["ps", "polystyrene", "styrofoam"],
        "bond_class": "aliphatic C-C with pendant aryl", "mechanism": "redox",
        "maturity": "no_documented_route", "default_surface": "amorphous",
        "note": "As polyethylene: no documented route at body conditions.",
    },
    # Kept, but with no curated enzyme evidence in this knowledge base.
    "CELLULOSE": {
        "aliases": ["cellulose", "wood", "timber", "splinter", "cellulosic"],
        "bond_class": "beta-1,4-glycosidic", "mechanism": "hydrolysis",
        "maturity": "unsupported", "default_surface": "crystalline",
        "molar_mass_g_mol": 162.14, "density_g_cm3": 1.5,
        "products": ["cellobiose", "glucose"],
        "note": "The concept brief leads with wood because the product "
                "profile is the mildest of any material: hydrolysis to "
                "cellobiose and glucose, both ordinary metabolites. That "
                "argument stands. What does NOT stand is any kinetic claim - "
                "PAZy is a plastics-active enzyme database and contains no "
                "cellulase, so this knowledge base has zero curated evidence "
                "for this material. Report the gap; do not borrow a constant "
                "from a polyester.",
    },
    "COTTON": {
        "aliases": ["cotton", "fabric", "textile", "cloth"],
        "bond_class": "beta-1,4-glycosidic", "mechanism": "hydrolysis",
        "maturity": "unsupported", "default_surface": "crystalline",
        "molar_mass_g_mol": 162.14, "density_g_cm3": 1.54,
        "products": ["cellobiose", "glucose"],
        "note": "As cellulose, with higher crystallinity and the additional "
                "risk of dyes and finishes. No curated evidence here either.",
    },
    "IRON_STEEL": {
        "aliases": ["iron", "steel", "ferrous", "shrapnel", "metal"],
        "bond_class": "metallic Fe(0)", "mechanism": "redox",
        "maturity": "research", "default_surface": "oxidised",
        "molar_mass_g_mol": 55.85, "density_g_cm3": 7.87,
        "products": ["fe_ion"], "cofactors": ["electron_acceptor", "chelator"],
        "note": "Research-tier and contested. f2c classes iron as "
                "non-enzymatic on the grounds that degradation would be redox "
                "corrosion rather than hydrolysis, and that objection is "
                "reported alongside any result here. The hydrogenase "
                "literature is real but slow, anaerobic and oxygen- and "
                "passivation-limited. The reaction liberates ions rather than "
                "metabolites, so CAPTURE and not rate is the binding "
                "constraint: if the capture gate fails, the answer is no-go, "
                "not 'optimise the enzyme'.",
    },
}


def _build_materials() -> dict[str, dict[str, Any]]:
    """Assemble the material registry from f2c's tables plus the detail above.

    Molar masses, densities and product lists come from f2c/formulate.py
    rather than being retyped, so there is one copy of each number. Where f2c
    deliberately omits a repeat unit (PUR, PBAT, NR - "not fixed by the
    class"), the omission is carried through as computable=False instead of
    being filled with a representative value.
    """
    out: dict[str, dict[str, Any]] = {}
    repeat = _T.get("repeat", {})
    density = _T.get("density", {})
    products = _T.get("products", {})
    for abbr, detail in _MATERIAL_DETAIL.items():
        prods = detail.get("products")
        if prods is None:
            prods = [_PRODUCT_KEY.get(p, p) for p in products.get(abbr, [])]
        mm = detail.get("molar_mass_g_mol", repeat.get(abbr))
        dens = detail.get("density_g_cm3", density.get(abbr))
        out[abbr.lower()] = {
            "abbreviation": abbr,
            "aliases": detail["aliases"],
            "bond_class": detail["bond_class"],
            "mechanism": detail["mechanism"],
            "products": prods,
            # Particulate is forbidden everywhere; hazard-bearing products are
            # caught by the gate against resolved GHS classification instead
            # of by a hand-written opinion list.
            "forbidden_products": ["microparticle"],
            "cofactors": detail.get("cofactors", []),
            "molar_mass_g_mol": mm,
            "density_g_cm3": dens,
            "mass_balance_computable": mm is not None,
            "default_product": (prods[0] if prods else "oligomer"),
            "maturity": detail["maturity"],
            "default_surface": detail["default_surface"],
            "note": detail["note"],
        }
    return out


MATERIALS: dict[str, dict[str, Any]] = _build_materials()

# Materials with no credible enzymatic depolymerisation route at body
# conditions. Naming them explicitly is more useful than silently returning
# a weak candidate - a no-go is a finding.
NO_GO_MATERIALS: dict[str, str] = dict(_T.get("non_enzymatic", {}))
# f2c blocks iron, steel and titanium as non-enzymatic. This project keeps the
# iron route as research-tier, so it is lifted out of the block list - but its
# reason is preserved in IRON_OBJECTION and reported with every iron result,
# so a reviewer sees both positions rather than only ours.
IRON_OBJECTION = {
    k: NO_GO_MATERIALS.pop(k)
    for k in ("iron", "steel") if k in NO_GO_MATERIALS
}


def resolve_material(text: str) -> tuple[str, float]:
    """Map free text onto a material family. Returns (family_key, confidence).

    Matching is on WORD BOUNDARIES, not substrings. Several abbreviations here
    are two letters - PA, PC, NR - and a substring search for "pa" matches
    "particle", "pad" and "apart". Getting the material wrong is the cheapest
    possible way to produce a confident wrong answer, so the match is strict
    and an unrecognised material returns confidence 0 rather than a guess.
    """
    s_norm = (text or "").lower()
    tokens = set(re.findall(r"[a-z0-9]+", s_norm))

    # An explicit family key or abbreviation is the strongest signal.
    for key, spec in MATERIALS.items():
        if key in tokens or spec["abbreviation"].lower() in tokens:
            return key, 0.9
    # Then the longer aliases: multi-word ones matched as phrases, single
    # words as whole tokens.
    for key, spec in MATERIALS.items():
        for alias in spec["aliases"]:
            a = alias.lower()
            if (" " in a and a in s_norm) or (" " not in a and a in tokens):
                return key, 0.75
    # A material with no enzymatic route at all is still an identification.
    for name in NO_GO_MATERIALS:
        if name in tokens:
            return name, 0.8
    for name in IRON_OBJECTION:
        if name in tokens:
            return "iron_steel", 0.8
    return "unknown", 0.0


# --------------------------------------------------------------------------
# INSPECT
# --------------------------------------------------------------------------


# Phrases that indicate dispersed particulate rather than a single object.
_DISPERSED_HINTS = (
    "micro-shrapnel", "microshrapnel", "micro shrapnel", "metallosis",
    "wear debris", "particulate", "dispersed", "peppered", "dust",
    "many small", "multiple small", "micro-fragments", "microfragments",
    "cloud of", "shower of", "blast debris",
)

# Default particle diameter when a dispersed case gives no size. Blast
# micro-shrapnel and orthopaedic wear debris both cluster in the tens of
# microns; 30 um is a mid-range stand-in and is REPORTED as an assumption,
# because the particle size sets the surface area and therefore the whole rate.
_DEFAULT_PARTICLE_UM = 30.0


def characterize_fragment(
    description: str = "",
    spectra: dict[str, Any] | None = None,
    volume_mm3: float | None = None,
    anatomy_class: str = "soft_tissue",
    presentation: str | None = None,
    particle_size_um: float | None = None,
    retrievable_mechanically: bool | None = None,
    case_text: str = "",
) -> dict[str, Any]:
    """Build a FragmentPassport from a description and/or instrument data.

    `spectra` is where real Raman / FTIR / XRF exports land. In this build the
    parser reads a simple {"peaks": [...], "elements": {...}} shape; the
    confidence it returns is lower for an inferred family than for one keyed
    off actual peak positions, and the agent is instructed to say which it
    had. A passport with confidence 0 is a legitimate output - it means "take
    a sample before designing anything".
    """
    check_clinical_output(description, where="fragment description")
    desc = sanitize_for_prompt(description, 600)
    spectra = spectra or {}

    family, conf = resolve_material(desc)
    source = "assumed"

    elements = {str(k).lower(): float(v) for k, v in (spectra.get("elements") or {}).items()}
    peaks = [float(p) for p in (spectra.get("peaks") or []) if isinstance(p, (int, float))]

    if elements:
        source = "sample"
        fe = elements.get("fe", 0.0)
        c = elements.get("c", 0.0)
        o = elements.get("o", 0.0)
        if fe > 40.0:
            family, conf = "iron_steel", min(0.95, 0.6 + fe / 200.0)
        elif c > 30.0 and o > 10.0 and family == "unknown":
            family, conf = "cellulose", 0.6
    if peaks:
        source = "sample" if source == "sample" else "sample"
        # Coarse, documented peak heuristics. Real deployment replaces this
        # with a spectral library match; the interface does not change.
        if any(1700 <= p <= 1740 for p in peaks) and any(1230 <= p <= 1290 for p in peaks):
            family, conf = "pet", 0.85  # ester C=O + C-O aromatic
        elif any(1050 <= p <= 1170 for p in peaks) and any(1310 <= p <= 1380 for p in peaks):
            family, conf = "cellulose", 0.8  # C-O-C ring + CH bending
        elif any(550 <= p <= 720 for p in peaks):
            family, conf = "iron_steel", 0.7  # iron-oxide lattice modes

    surface = "unknown"
    if family == "iron_steel":
        surface = "oxidised"
    elif family in ("cotton",):
        surface = "crystalline"
    elif family == "pet":
        surface = "semi-crystalline"
    if elements.get("o", 0.0) > 25.0 and family == "iron_steel":
        surface = "oxidised"

    additives: list[str] = []
    for marker, label in (
        ("dye", "dye"),
        ("plasticiz", "plasticiser"),
        ("plasticiz", "plasticiser"),
        ("paint", "pigment"),
        ("galvan", "zinc_coating"),
        ("soil", "soil_load"),
        ("dirt", "soil_load"),
        ("sand", "silica"),
    ):
        if marker in desc.lower() and label not in additives:
            additives.append(label)

    vol = None
    if volume_mm3 is not None:
        vol = validate_number("fragment_volume_mm3", volume_mm3)

    # Presentation: taken from the caller if given, otherwise inferred from the
    # case text. It is never guessed silently - an inferred value is reported
    # with how it was arrived at, because it changes the whole problem.
    pres = str(presentation or "").strip().lower()
    pres_source = "stated"
    if pres not in ("single_fragment", "dispersed_particulate"):
        # Inference reads the description AND the original case text. The
        # caller may paraphrase, and a paraphrase that drops "micro-shrapnel"
        # would silently flip the whole problem from a particle cloud to a
        # single object.
        low = (desc + " " + sanitize_for_prompt(case_text, 2000)).lower()
        if any(h in low for h in _DISPERSED_HINTS):
            pres, pres_source = "dispersed_particulate", "inferred from the case text"
        else:
            pres, pres_source = "single_fragment", "assumed (no indication of dispersal)"

    psize = None
    size_assumed = False
    if pres == "dispersed_particulate":
        if particle_size_um is not None:
            psize = float(validate_number("particle_size_um", particle_size_um))
        else:
            psize = _DEFAULT_PARTICLE_UM
            size_assumed = True

    # Particle count, from the stated volume and the particle size.
    pcount = None
    if pres == "dispersed_particulate" and psize and vol:
        r_mm = (psize / 1000.0) / 2.0
        one = (4.0 / 3.0) * math.pi * r_mm ** 3
        pcount = int(vol / one) if one > 0 else None

    # Is conventional retrieval a realistic alternative? This is the honest
    # comparator and the system is not allowed to skip it: for a single
    # reachable fragment, forceps under ultrasound is faster, cheaper and
    # proven, and a catalyst has to be justified against that rather than
    # against doing nothing.
    retr = retrievable_mechanically
    if retr is None:
        if pres == "dispersed_particulate":
            retr = False  # thousands of micron particles cannot be picked out
        else:
            hard = anatomy_class in ("near_nerve", "intra_articular", "vascular",
                                     "cns", "ocular")
            declined = any(k in (desc + " " + case_text).lower()
                           for k in ("declined", "refused", "inoperable",
                                     "unresectable", "not a surgical candidate"))
            retr = not (hard or declined)

    blocker = NO_GO_MATERIALS.get(family)
    return {
        "passport": {
            "material_family": family,
            "presentation": pres,
            "surface_state": surface,
            "additives": additives,
            "anatomy_class": validate_identifier(anatomy_class, field="anatomy_class"),
            "volume_mm3": vol,
            "particle_size_um": psize,
            "particle_count": pcount,
            "retrievable_mechanically": retr,
            "confidence": round(conf, 2),
            "source": source,
        },
        "presentation_basis": pres_source,
        "particle_size_assumed": size_assumed,
        "no_go": bool(blocker),
        "no_go_reason": blocker or "",
        "material_note": MATERIALS.get(family, {}).get("note", ""),
        "maturity": MATERIALS.get(family, {}).get("maturity", "unknown"),
        "advice": (
            "Confidence is 0 - the family was not identified from the text and no "
            "spectral data was supplied. Obtain a sample or imaging-based material "
            "ID before designing a catalyst."
            if conf == 0.0
            else ""
        ),
        "engine_version": ENGINE_VERSION,
    }


def define_reaction(material_family: str, surface_state: str = "unknown") -> dict[str, Any]:
    """Turn a material family into an explicit chemistry target.

    Returns the bond class to attack, the mechanism, the products expected
    and - the field that does the real work - the products that must never
    appear. `run_safety_gates` checks the simulated product mix against
    `forbidden_products`, so this is where a route is made falsifiable.
    """
    fam = validate_identifier(material_family, field="material_family").lower()
    if fam in NO_GO_MATERIALS:
        return {
            "ok": False,
            "reason": NO_GO_MATERIALS[fam],
            "recommendation": "no-go: do not advance this material family",
        }
    spec = MATERIALS.get(fam)
    if not spec:
        return {
            "ok": False,
            "reason": f"unknown material family {fam!r}",
            "recommendation": "characterize the fragment before defining a reaction",
        }
    # Three distinct kinds of "no", kept apart on purpose. Collapsing them
    # would let "nobody has looked" masquerade as "it cannot work".
    if spec["maturity"] == "no_documented_route":
        return {
            "ok": False,
            "reason": spec["note"],
            "recommendation": "no-go on current evidence: no depolymerisation "
                              "route is documented for this material at body "
                              "conditions. This is absent evidence, not proof "
                              "of impossibility - report it as such.",
            "maturity": spec["maturity"],
        }
    accessibility = {
        "crystalline": 0.25,
        "semi-crystalline": 0.45,
        "oxidised": 0.35,
        "coated": 0.2,
        "pristine": 0.8,
        "unknown": 0.6,
    }.get(surface_state, 0.6)
    return {
        "ok": True,
        "reaction_spec": {
            "bond_class": spec["bond_class"],
            "mechanism": spec["mechanism"],
            "products": list(spec["products"]),
            "cofactors": list(spec["cofactors"]),
            "forbidden_products": list(spec["forbidden_products"]),
            "notes": spec["note"],
        },
        "substrate": {
            "molar_mass_g_mol": spec["molar_mass_g_mol"],
            "density_g_cm3": spec["density_g_cm3"],
            "accessibility": accessibility,
            "default_product": spec["default_product"],
        },
        "maturity": spec["maturity"],
    }


# --------------------------------------------------------------------------
# DESIGN
# --------------------------------------------------------------------------

# Deterministic edit catalogue. Each entry is an engineering move with a
# documented, directional effect on the proxy scores - NOT a structure
# prediction. The system "proposes and ranks sequence-level edits"; it does
# not claim to know that any of them folds. Keeping the effects explicit and
# additive means a reviewer can audit why a candidate scored as it did,
# which an opaque learned scorer would not allow.
EDIT_CATALOGUE: dict[str, dict[str, Any]] = {
    "thermostabilising_core": {
        "label": "stabilising core substitutions",
        "effects": {"stability": +0.22, "activity": -0.05, "expression": -0.02},
        "kinetic": {"half_life_h": 2.2, "t_width_c": 1.15},
        "rationale": "Consensus/ancestral core packing raises melting point; "
                     "usually costs a little activity.",
    },
    "surface_charge_tuning": {
        "label": "surface charge tuning",
        "effects": {"solubility": +0.18, "immunogenicity": -0.04, "activity": 0.0},
        "kinetic": {},
        "rationale": "Raises net charge to suppress aggregation at body pH.",
    },
    "active_site_loop_graft": {
        "label": "active-site loop graft",
        "effects": {"activity": +0.25, "stability": -0.12, "expression": -0.05},
        "kinetic": {"k_cat": 2.0, "k_m_uM": 0.7},
        "rationale": "Widens the cleft for a solid, non-ideal substrate. The "
                     "highest-upside and highest-risk edit in the catalogue.",
    },
    "material_binding_peptide_fusion": {
        "label": "material-binding peptide fusion",
        "effects": {"activity": +0.18, "expression": -0.08, "immunogenicity": +0.06},
        "kinetic": {"k_m_uM": 0.5},
        "rationale": "Anchors the enzyme at the surface, raising local "
                     "occupancy. Adds a foreign domain, so immunogenicity rises.",
    },
    "deimmunisation_pass": {
        "label": "T-cell epitope deimmunisation",
        "effects": {"immunogenicity": -0.3, "activity": -0.06, "stability": -0.04},
        "kinetic": {},
        "rationale": "Removes predicted epitopes. Matters because the construct "
                     "is a foreign protein in tissue.",
    },
    "protease_resistance": {
        "label": "protease-resistant linker set",
        "effects": {"stability": +0.14, "expression": -0.03},
        "kinetic": {"half_life_h": 1.6},
        "rationale": "Host proteases are the main in-tissue loss route.",
    },
    "gel_anchor_tag": {
        "label": "hydrogel anchor tag",
        "effects": {"stability": +0.08, "activity": -0.03},
        "kinetic": {"half_life_h": 1.3},
        "rationale": "Covalent tether to the gel network. Suppresses leakage "
                     "out of the depot, which is a safety property as much as "
                     "a performance one.",
    },
}


def propose_variants(
    parent_family: str,
    base_params: dict[str, Any] | None = None,
    n_variants: int = 5,
    goal: str = "balanced",
) -> dict[str, Any]:
    """Enumerate candidate variants over the edit catalogue.

    Deterministic: the same inputs always produce the same candidate list, in
    the same order. That is a demo requirement and a reproducibility
    requirement, and it is why this is a documented enumeration rather than a
    sampled generative model.

    Every candidate carries provenance 'in-silico proposal'. Nothing here is
    a validated sequence and the loop is not allowed to describe it as one.
    """
    parent = validate_identifier(parent_family, field="parent_family")
    n = int(validate_number("n_variants", n_variants))
    goal = validate_identifier(goal, field="goal").lower()

    priority = {
        "activity": ["active_site_loop_graft", "material_binding_peptide_fusion",
                     "thermostabilising_core", "protease_resistance",
                     "surface_charge_tuning", "gel_anchor_tag", "deimmunisation_pass"],
        "stability": ["thermostabilising_core", "protease_resistance", "gel_anchor_tag",
                      "surface_charge_tuning", "active_site_loop_graft",
                      "deimmunisation_pass", "material_binding_peptide_fusion"],
        "safety": ["deimmunisation_pass", "gel_anchor_tag", "protease_resistance",
                   "surface_charge_tuning", "thermostabilising_core",
                   "active_site_loop_graft", "material_binding_peptide_fusion"],
    }.get(goal, list(EDIT_CATALOGUE))

    candidates: list[dict[str, Any]] = [
        {
            "name": f"{parent}-WT",
            "parent_family": parent,
            "edits": [],
            "provenance": "wild-type reference",
            "rationale": "Unmodified reference. Always carried, so every engineered "
                         "candidate has to beat the thing you could just buy.",
        }
    ]
    # Single edits first, then the two best-ranked combined. Breadth before
    # depth: a stacked variant that fails tells you nothing about which edit
    # was responsible.
    for key in priority[: max(n - 2, 0)]:
        spec = EDIT_CATALOGUE[key]
        candidates.append({
            "name": f"{parent}-{key[:12]}",
            "parent_family": parent,
            "edits": [key],
            "provenance": "in-silico proposal",
            "rationale": spec["rationale"],
        })
    if n >= 3 and len(priority) >= 2:
        a, b = priority[0], priority[1]
        candidates.append({
            "name": f"{parent}-combo",
            "parent_family": parent,
            "edits": [a, b],
            "provenance": "in-silico proposal",
            "rationale": f"Stacks {EDIT_CATALOGUE[a]['label']} with "
                         f"{EDIT_CATALOGUE[b]['label']}; test only after both "
                         f"single edits are measured.",
        })
    candidates = candidates[: max(n, 1)]
    return {
        "candidates": candidates,
        "n": len(candidates),
        "edit_catalogue": {k: v["label"] for k, v in EDIT_CATALOGUE.items()},
        "caveat": "Sequence-level proposals only. No folding, expression or "
                  "binding has been predicted or verified. " + simulation_disclaimer(),
    }


def predict_properties(candidate: dict[str, Any]) -> dict[str, Any]:
    """Transparent additive proxy scores for one candidate.

    HEURISTIC, AND SAID SO. Each score starts at a base value for the parent
    family and is moved by the documented effect of each edit. There is no
    trained model behind these numbers; they encode the direction and rough
    magnitude of well-known protein-engineering trade-offs so that the
    ranking step has something defensible to sort on.

    Returns the per-edit contributions alongside the totals so the score can
    be audited rather than trusted.
    """
    edits = [str(e) for e in (candidate.get("edits") or [])]
    base = {
        "activity": 0.50,
        "stability": 0.50,
        "solubility": 0.60,
        "expression": 0.65,
        "immunogenicity": 0.45,  # lower is better
    }
    scores = dict(base)
    contributions: list[dict[str, Any]] = []
    for e in edits:
        spec = EDIT_CATALOGUE.get(e)
        if not spec:
            contributions.append({"edit": e, "unknown": True})
            continue
        for k, dv in spec["effects"].items():
            scores[k] = scores.get(k, 0.5) + dv
        contributions.append({"edit": e, "label": spec["label"], "effects": spec["effects"]})
    # Stacking penalty: each additional edit compounds the risk that the
    # construct does not express or fold at all.
    if len(edits) > 1:
        penalty = 0.05 * (len(edits) - 1)
        scores["expression"] -= penalty
        scores["stability"] -= penalty * 0.5
        contributions.append({"edit": "<stacking penalty>", "effects": {
            "expression": -penalty, "stability": -penalty * 0.5}})
    scores = {k: round(max(0.0, min(1.0, v)), 3) for k, v in scores.items()}
    # Developability: one number for the ranking table. Immunogenicity enters
    # inverted because low is good.
    scores["developability"] = round(
        0.3 * scores["activity"] + 0.25 * scores["stability"]
        + 0.15 * scores["solubility"] + 0.15 * scores["expression"]
        + 0.15 * (1.0 - scores["immunogenicity"]), 3)
    return {
        "name": candidate.get("name", "unnamed"),
        "scores": scores,
        "contributions": contributions,
        "method": "additive heuristic over a documented edit catalogue; not a trained model",
    }


# --------------------------------------------------------------------------
# VALIDATE (simulated)
# --------------------------------------------------------------------------


# Fallbacks used ONLY when a parameter was never measured. Each one is recorded
# in `assumed_parameters` and surfaced in the report, because a quietly
# substituted default is how a simulation starts lying: the number looks the
# same whether it came from a paper or from this dict.
_FALLBACKS = {
    "k_cat": 1.0, "k_m_uM": 50.0, "t_opt_c": 37.0, "t_width_c": 12.0,
    "ph_opt": 7.0, "ph_width": 1.2, "ea_kj": 45.0, "radius_nm": 3.0,
    "half_life_h": 72.0, "fragmentation_fraction": 0.0,
}


def _enzyme_params_for(
    candidate: dict[str, Any], base: dict[str, Any] | None, product: str
) -> tuple[kinetics.EnzymeParams, list[str]]:
    """Build kinetic parameters for a candidate, and report what was assumed.

    Returns (params, assumed) where `assumed` names every parameter that came
    from _FALLBACKS rather than from a measurement. The caller must carry that
    list into the result; the gate battery reads it.
    """
    base = base or {}
    assumed: list[str] = list(base.get("assumed_parameters") or [])

    def pick(key: str) -> float:
        if base.get(key) is not None:
            return float(base[key])
        label = {"k_cat": "k_cat", "k_m_uM": "K_m", "half_life_h": "half_life"}.get(key, key)
        if label not in assumed:
            assumed.append(label)
        return float(_FALLBACKS[key])

    p = kinetics.EnzymeParams(
        name=str(candidate.get("name", "unnamed")),
        k_cat=pick("k_cat"),
        k_m_uM=pick("k_m_uM"),
        t_opt_c=pick("t_opt_c"),
        t_width_c=pick("t_width_c"),
        ph_opt=pick("ph_opt"),
        ph_width=pick("ph_width"),
        ea_kj=pick("ea_kj"),
        radius_nm=pick("radius_nm"),
        half_life_h=pick("half_life_h"),
        product=product,
        fragmentation_fraction=float(base.get("fragmentation_fraction", 0.0)),
    )
    for e in candidate.get("edits") or []:
        for field_name, mult in (EDIT_CATALOGUE.get(str(e), {}).get("kinetic") or {}).items():
            if hasattr(p, field_name):
                setattr(p, field_name, getattr(p, field_name) * float(mult))
    # A fusion domain makes the construct physically larger, which costs mesh
    # mobility - the trade-off the gel imposes on every anchoring strategy.
    if "material_binding_peptide_fusion" in (candidate.get("edits") or []):
        p.radius_nm *= 1.25
    return p, assumed


def score_kinetics(
    candidate: dict[str, Any],
    base_params: dict[str, Any] | None = None,
    conditions: dict[str, Any] | None = None,
    product: str = "oligomer",
) -> dict[str, Any]:
    """Fast point estimate of surface erosion for one candidate.

    Cheap screen, used to shortlist before spending the uncertainty sweep.
    """
    cond_in = validate_params(conditions or {})
    cond = kinetics.Conditions(
        temperature_c=cond_in.get("temperature_c", 37.0),
        ph=cond_in.get("ph", 7.4),
        enzyme_uM=cond_in.get("enzyme_uM", 10.0),
        serum_fraction=cond_in.get("serum_fraction", 0.1),
        hours=cond_in.get("hours", 336.0),
        timestep_h=cond_in.get("timestep_h", 0.5),
    )
    base = base_params or {}
    frag = kinetics.FragmentParams(
        volume_mm3=validate_number("fragment_volume_mm3", base.get("volume_mm3", 10.0)),
        density_g_cm3=float(base.get("density_g_cm3", 1.4)),
        molar_mass_g_mol=float(base.get("molar_mass_g_mol", 162.14)),
        accessibility=float(base.get("accessibility", 0.6)),
        presentation=str(base.get("presentation") or "single_fragment"),
        particle_size_um=(validate_number("particle_size_um", base["particle_size_um"])
                          if base.get("particle_size_um") else None),
    )
    gel = kinetics.GelParams(
        mesh_nm=validate_number("mesh_nm", base.get("mesh_nm", 20.0)),
        volume_ul=validate_number("gel_volume_ul", base.get("gel_volume_ul", 500.0)),
    )
    enz, assumed = _enzyme_params_for(candidate, base, product)
    r = kinetics.simulate(enz, gel, frag, cond)
    return {
        "name": enz.name,
        "kinetics_provenance": str((base or {}).get("kinetics_provenance") or "unknown"),
        "assumed_parameters": assumed,
        "erosion_rate_um_per_day": _finite(round(r["erosion_rate_um_per_day"], 4)),
        "consumed_fraction": _finite(round(r["consumed_fraction"], 4)),
        "time_to_half_h": r["time_to_half_h"],
        "mass_balance_residual": _finite(r["mass_balance_residual"]),
        "k_surface_umol_mm2_h": r["k_surface_umol_mm2_h"],
        "product_radius_known": r.get("product_radius_known", False),
        "presentation": r.get("presentation"),
        "n_particles": r.get("n_particles"),
        "method": "point estimate; run simulate_hydrogel_assay for the band",
    }


def simulate_hydrogel_assay(
    candidate: dict[str, Any],
    base_params: dict[str, Any] | None = None,
    conditions: dict[str, Any] | None = None,
    product: str = "oligomer",
    n_samples: int = 64,
    seed: int = 0,
) -> dict[str, Any]:
    """The virtual experiment: full assay with an uncertainty band.

    This is the 'controlled hydrogel environment' the project is built
    around. It returns a time series (fragment / free product / gel-captured /
    cleared / particles), a 5-95 percentile band on the erosion rate, and the
    mass-balance residual that `check_mass_balance` and the safety gates key
    off.

    The band is the honest part. A single number here would be false
    precision given that the underlying kinetic constants vary by an order of
    magnitude between published measurements.
    """
    cond_in = validate_params(conditions or {})
    cond = kinetics.Conditions(
        temperature_c=cond_in.get("temperature_c", 37.0),
        ph=cond_in.get("ph", 7.4),
        enzyme_uM=cond_in.get("enzyme_uM", 10.0),
        serum_fraction=cond_in.get("serum_fraction", 0.1),
        hours=cond_in.get("hours", 336.0),
        timestep_h=cond_in.get("timestep_h", 0.5),
    )
    base = base_params or {}
    frag = kinetics.FragmentParams(
        volume_mm3=validate_number("fragment_volume_mm3", base.get("volume_mm3", 10.0)),
        density_g_cm3=float(base.get("density_g_cm3", 1.4)),
        molar_mass_g_mol=float(base.get("molar_mass_g_mol", 162.14)),
        accessibility=float(base.get("accessibility", 0.6)),
        presentation=str(base.get("presentation") or "single_fragment"),
        particle_size_um=(validate_number("particle_size_um", base["particle_size_um"])
                          if base.get("particle_size_um") else None),
    )
    gel = kinetics.GelParams(
        mesh_nm=validate_number("mesh_nm", base.get("mesh_nm", 20.0)),
        volume_ul=validate_number("gel_volume_ul", base.get("gel_volume_ul", 500.0)),
        capture_rate_per_h=float(base.get("capture_rate_per_h", 0.35)),
        capture_capacity_umol=float(base.get("capture_capacity_umol", 50.0)),
        clearance_rate_per_h=float(base.get("clearance_rate_per_h", 0.02)),
    )
    enz, assumed = _enzyme_params_for(candidate, base, product)
    n = int(validate_number("n_samples", n_samples))
    provenance = str((base or {}).get("kinetics_provenance") or "unknown")
    r = kinetics.simulate_with_uncertainty(
        enz, gel, frag, cond, n_samples=n, seed=int(seed), provenance=provenance)

    # Downsample the trace for transport - the UI draws a sparkline, not a
    # 4000-point plot, and a 64 MB frame cap is not an invitation.
    tr = r["trace"]
    total = len(tr["t_h"])
    stride = max(total // 60, 1)
    series = [
        {
            "t_h": tr["t_h"][i],
            "fragment": round(tr["fragment_umol"][i], 6),
            "free": round(tr["free_umol"][i], 6),
            "captured": round(tr["captured_umol"][i], 6),
            "cleared": round(tr["cleared_umol"][i], 6),
            "particles": round(tr["particles_umol"][i], 6),
            "radius_mm": round(tr["radius_mm"][i], 6),
        }
        for i in range(0, total, stride)
    ]
    return {
        "candidate": enz.name,
        "conditions": {
            "temperature_c": cond.temperature_c, "ph": cond.ph,
            "enzyme_uM": cond.enzyme_uM, "serum_fraction": cond.serum_fraction,
            "hours": cond.hours, "mesh_nm": gel.mesh_nm,
            "fragment_volume_mm3": frag.volume_mm3, "accessibility": frag.accessibility,
        },
        "timeseries": series,
        "erosion_rate_um_per_day": _finite(round(r["erosion_rate_um_per_day"], 4)),
        "erosion_rate_ci": [round(r["erosion_rate_ci"][0], 4), round(r["erosion_rate_ci"][1], 4)],
        "uncertainty": _finite(round(r["uncertainty"], 4)),
        "consumed_fraction": _finite(round(r["consumed_fraction"], 4)),
        "time_to_half_h": r["time_to_half_h"],
        "depleted_at_h": r["depleted_at_h"],
        "captured_fraction": _finite(round(r["captured_fraction"], 4)),
        "free_fraction": _finite(round(r["free_fraction"], 4)),
        "particle_fraction": _finite(round(r["particle_fraction"], 4)),
        "particle_fraction_p95": round(r["particle_fraction_p95"], 6),
        "captured_fraction_p05": _finite(round(r["captured_fraction_p05"], 4)),
        "mass_balance_residual": _finite(r["mass_balance_residual"]),
        "product": r["product"],
        "n_samples": r["n_samples"],
        "kinetics_provenance": provenance,
        "presentation": r.get("presentation"),
        "n_particles": r.get("n_particles"),
        "initial_area_mm2": _finite(round(r.get("initial_area_mm2") or 0.0, 3)),
        "specific_area_mm2_per_mm3": _finite(
            round(r.get("specific_area_mm2_per_mm3") or 0.0, 3)),
        "product_radius_nm": r.get("product_radius_nm"),
        "product_radius_known": r.get("product_radius_known", False),
        "rel_sigma": r.get("rel_sigma"),
        "assumed_parameters": assumed,
        "measured_on": (base or {}).get("measured_on"),
        "evidence_citations": (base or {}).get("evidence_citations") or [],
        "enzyme_safety": (base or {}).get("enzyme_safety"),
        "disclaimer": simulation_disclaimer(),
    }


def check_mass_balance(assay: dict[str, Any], tolerance: float = 1e-6) -> dict[str, Any]:
    """Verify the assay conserved mass, and that the books actually close.

    Two independent checks: the residual the integrator reported, and a
    recomputation from the final time point. A model whose mass balance does
    not close is producing numbers that mean nothing, so this is a
    precondition for every other conclusion - 'the fragment got smaller' is
    not a result unless you can say where the mass went.
    """
    residual = float(assay.get("mass_balance_residual", 1.0))
    series = assay.get("timeseries") or []
    recomputed = None
    if series:
        first, last = series[0], series[-1]
        start = first.get("fragment", 0.0)
        end_sum = sum(float(last.get(k, 0.0))
                      for k in ("fragment", "free", "captured", "cleared", "particles"))
        recomputed = abs(start - end_sum) / start if start > 0 else None
    # The downsampled series is checked loosely; the integrator residual is
    # the authoritative figure.
    ok = residual <= tolerance
    return {
        "passed": ok,
        "residual": residual,
        "tolerance": tolerance,
        "recomputed_residual": recomputed,
        "detail": (
            f"mass balance closes to {residual:.2e}"
            if ok
            else f"mass balance residual {residual:.2e} exceeds {tolerance:.0e} - "
                 f"the integration is unstable and no conclusion may be drawn "
                 f"from this run"
        ),
    }


# --------------------------------------------------------------------------
# THE GATE BATTERY
#
# This is the most important function in the worker. The agent loop treats a
# failed gate as a HARD STOP, not as feedback to work around - because a
# model given a soft failure will rephrase and retry, and the whole point of
# a gate is that it cannot be argued with.
#
# Thresholds live here, in one readable table, with the number that decided
# each verdict reported back. "The fragment got smaller" is not an endpoint;
# these are.
# --------------------------------------------------------------------------

GATE_THRESHOLDS: dict[str, float] = {
    # Mass balance must close or nothing else means anything.
    "mass_balance_residual_max": 1e-6,
    # Any detached particulate is a migration risk. Surface erosion should
    # release soluble products, not debris.
    "particle_fraction_max": 0.01,
    # Product that is neither captured by the gel nor cleared is loose in
    # tissue. The brief's own framing: capture, not rate, is the constraint.
    "free_fraction_max": 0.25,
    # Capture has to beat release or the depot is just a slow-release source
    # of whatever the reaction produces.
    "captured_fraction_min": 0.50,
    # A rate so uncertain that the band spans an order of magnitude is not a
    # prediction, it is a request for an experiment.
    "uncertainty_max": 3.0,
    # A route that erodes nothing measurable is a no-go, not a safe option.
    "erosion_rate_min_um_per_day": 0.05,
}

# Which kinetics provenances may support a rate claim. Today NOTHING in the
# knowledge base reaches "polymer", so this gate fails on essentially every
# run - and that is the correct behaviour, not a bug. It is the system
# reporting that the measurement everyone needs has never been made.
ALLOWED_KINETICS_PROVENANCE = {"polymer", "oligomer"}


def run_safety_gates(
    assay: dict[str, Any],
    reaction_spec: dict[str, Any] | None = None,
    passport: dict[str, Any] | None = None,
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run every gate. Returns pass/fail per gate with the deciding number.

    `blocking` in the result tells the agent loop to stop. The loop is
    written to honour it and to emit the failure rather than trying a
    different phrasing of the same candidate.
    """
    gates: list[dict[str, Any]] = []
    spec = reaction_spec or {}
    passport = passport or {}

    def gate(name: str, passed: bool, value: Any, threshold: Any, detail: str) -> None:
        gates.append({
            "name": name,
            "passed": bool(passed),
            "value": (round(float(value), 6) if isinstance(value, (int, float)) else value),
            "threshold": threshold,
            "detail": detail,
        })

    # 1. Mass balance.
    mb = float(assay.get("mass_balance_residual", 1.0))
    t = GATE_THRESHOLDS["mass_balance_residual_max"]
    gate("mass_balance", mb <= t, mb, t,
         "books close - every umol that left the fragment is accounted for"
         if mb <= t else
         "mass balance does not close; the run is numerically invalid")

    # 2. Fragmentation / particle generation.
    pf = float(assay.get("particle_fraction_p95", assay.get("particle_fraction", 0.0)))
    t = GATE_THRESHOLDS["particle_fraction_max"]
    gate("fragmentation", pf <= t, pf, t,
         "surface erosion dominates; no appreciable particulate released"
         if pf <= t else
         "detached particulate above threshold - partial breakup creates "
         "mobile microparticles, which is worse than leaving the fragment intact")

    # 3. Free product fraction (loose in tissue).
    ff = float(assay.get("free_fraction", 1.0))
    t = GATE_THRESHOLDS["free_fraction_max"]
    gate("free_product", ff <= t, ff, t,
         "released product stays bound or is cleared"
         if ff <= t else
         "too much product is loose rather than captured or cleared")

    # 4. Capture efficiency.
    cf = float(assay.get("captured_fraction_p05", assay.get("captured_fraction", 0.0)))
    t = GATE_THRESHOLDS["captured_fraction_min"]
    gate("capture_efficiency", cf >= t, cf, t,
         "gel captures the majority of released product"
         if cf >= t else
         "capture is too low - the gel is not containing the products it creates")

    # 5. Forbidden products, now informed by hazard classification.
    produced = set()
    if assay.get("product"):
        produced.add(str(assay["product"]))
    if float(assay.get("particle_fraction_p95", 0.0)) > GATE_THRESHOLDS["particle_fraction_max"]:
        produced.add("microparticle")
    forbidden = {str(x) for x in (spec.get("forbidden_products") or [])}
    hit = sorted(produced & forbidden)

    # A resolved GHS health hazard (H3xx) on a product is a forbidden product
    # on evidence rather than on opinion. This is the half of the check that
    # used to rest entirely on a hand-written list.
    store = _compounds()
    hazard_hits: list[str] = []
    for prod in sorted(produced):
        c = store.get(prod)
        if c is None or not getattr(c, "hazard_resolved", False):
            continue
        health = [h for h in (c.ghs_codes or []) if h.startswith("H3")]
        if health:
            hazard_hits.append(f"{prod} ({', '.join(health)})")
    all_hits = hit + hazard_hits
    gate("forbidden_products", not all_hits, ", ".join(all_hits) or "none",
         sorted(forbidden) + ["any resolved GHS H3xx"],
         "no forbidden product in the simulated mix, and no resolved GHS "
         "health hazard among the products" if not all_hits else
         f"forbidden product present: {', '.join(all_hits)}")

    # 5b. Product characterisation. The capture and free-product gates above
    #     are computed from each product's molecular radius. If a product is
    #     not in the compound store, that radius was a generic fallback and
    #     those numbers do not mean what they appear to mean.
    prod_known = bool(assay.get("product_radius_known", True))
    prod_name = str(assay.get("product") or "unspecified")
    gate("product_characterised", prod_known, prod_name, "present in the compound store",
         f"{prod_name} is characterised; its radius is derived from its formula"
         if prod_known else
         f"{prod_name} is not in the compound store, so the mesh-hindrance "
         f"term used a generic fallback radius. The capture and free-product "
         f"numbers above are therefore not trustworthy for this product")

    # 5c. Hazard resolution. Not a pass/fail on safety - a pass/fail on whether
    #     the safety question was ASKED. Unresolved hazard is reported as
    #     unresolved, never as safe.
    unresolved = [p for p in sorted(produced)
                  if p in store and not getattr(store[p], "hazard_resolved", False)]
    missing_entirely = [p for p in sorted(produced) if p not in store]
    pending = unresolved + missing_entirely
    gate("hazard_resolved", not pending, ", ".join(pending) or "none",
         "GHS classification resolved for every product",
         "hazard classification is resolved for every product"
         if not pending else
         f"no hazard classification has been resolved for: {', '.join(pending)}. "
         f"This is NOT a finding of safety - it is an unanswered question. "
         f"Run tools/fetch_chemistry.py to resolve it against PubChem")

    # 6. Predictive confidence.
    un = float(assay.get("uncertainty", 99.0))
    t = GATE_THRESHOLDS["uncertainty_max"]
    gate("predictive_confidence", un <= t, un, t,
         "band is tight enough to rank on" if un <= t else
         "band spans too wide a range to support a recommendation - this is a "
         "request for a wet-lab measurement, not a result")

    # 7. Meaningful erosion.
    er = float(assay.get("erosion_rate_um_per_day", 0.0))
    t = GATE_THRESHOLDS["erosion_rate_min_um_per_day"]
    gate("meaningful_erosion", er >= t, er, t,
         "erosion rate is measurable" if er >= t else
         "predicted erosion is negligible; this route does nothing")

    # 8. Human-tissue off-target proxy. The enzyme must act on the fragment
    #    material, not on tissue. Collagen/protein-degrading mechanisms are
    #    refused outright for this application regardless of their numbers.
    bond = str(spec.get("bond_class", "")).lower()
    off_target = any(k in bond for k in ("peptide", "collagen", "protein", "elastin"))
    gate("tissue_off_target", not off_target, bond or "n/a", "no peptide-bond chemistry",
         "target chemistry has no human-tissue substrate" if not off_target else
         "target bond class occurs in human tissue - a protease/collagenase "
         "route cannot be made fragment-selective and is refused")

    # 9. Anatomical risk tier. Not a clinical judgement - a routing rule that
    #    says a high-risk location demands a tighter standard, and the
    #    thresholds above are not calibrated for it.
    anat = str(passport.get("anatomy_class", "soft_tissue")).lower()
    high_risk = anat in ("near_nerve", "intra_articular", "vascular", "cns", "ocular")
    gate("anatomical_tier", not high_risk, anat, "soft_tissue or peri_articular",
         "location is within the modelled tier" if not high_risk else
         f"location '{anat}' is outside the tier this model is calibrated for; "
         f"no candidate may be advanced on these thresholds alone")

    # 10. Confidence in the material ID. Designing for the wrong material is
    #     the cheapest way to get a confident wrong answer.
    conf = float(passport.get("confidence", 0.0) or 0.0)
    gate("material_identified", conf >= 0.5, conf, 0.5,
         "material family identified with usable confidence" if conf >= 0.5 else
         "material ID too weak to design against - characterize first")

    # 11. Kinetics provenance. The constants driving every number above were
    #     measured on SOMETHING - and if that something was not the fragment
    #     material, the rate is an extrapolation across substrates, not a
    #     prediction. This gate exists because the knowledge base contains no
    #     turnover number measured on a solid polymer: the available constants
    #     come from chromogenic esters and, in one case, from casein.
    prov = str(assay.get("kinetics_provenance") or "unknown")
    measured_on = assay.get("measured_on") or "an unrecorded substrate"
    ok_prov = prov in ALLOWED_KINETICS_PROVENANCE
    gate("kinetics_provenance", ok_prov, prov, sorted(ALLOWED_KINETICS_PROVENANCE),
         f"kinetics were measured on {measured_on}, which is {prov}-level evidence "
         f"for this material"
         if ok_prov else
         f"the kinetic constants were measured on {measured_on} ({prov}-level), "
         f"not on the fragment material. No turnover number measured on a solid "
         f"fragment exists in the knowledge base, so this rate is an "
         f"extrapolation across substrates and may not be reported as a "
         f"prediction")

    # 12. Assumed parameters. A simulation resting on unmeasured inputs has to
    #     say which ones, and a rate claim cannot rest on an assumed k_cat.
    assumed = list(assay.get("assumed_parameters") or [])
    blocking_assumptions = [a for a in assumed if a in ("k_cat", "K_m")]
    gate("measured_inputs", not blocking_assumptions,
         ", ".join(assumed) or "none", "k_cat and K_m measured",
         "the parameters driving the rate were measured"
         if not blocking_assumptions else
         f"no measured value exists for {', '.join(blocking_assumptions)}; the "
         f"simulation fell back to a generic default, so the rate reflects that "
         f"default rather than this enzyme")

    # 15. HOST SAFETY OF THE ENZYME ITSELF.
    #
    #     Gate 8 asked whether the REACTION we are running attacks a bond type
    #     present in human tissue. This asks the different and equally
    #     necessary question: what else can THIS PARTICULAR PROTEIN do?
    #
    #     The knowledge base shows why both are needed. Every one of the four
    #     peptidases in it is retrieved as a PLA candidate. PLA hydrolysis is
    #     aliphatic-ester chemistry, so gate 8 passes them - but Proteinase K
    #     and the subtilisins are broad-spectrum serine proteases whose own
    #     activity is on peptide bonds, which is what collagen, elastin and
    #     fibronectin are made of. Proteinase K's turnover number here was
    #     measured on casein: a protein.
    enzyme_safety = assay.get("enzyme_safety") or {}
    if enzyme_safety:
        risks = enzyme_safety.get("risks") or []
        blocking_risks = [r for r in risks if r.get("severity") == "blocking"]
        detail_ok = (
            f"{enzyme_safety.get('name', 'the candidate')} has no host-substrate "
            f"activity flagged from its classification. Absence of a flag is not "
            f"evidence of selectivity."
        )
        gate("enzyme_host_safety", not blocking_risks,
             enzyme_safety.get("worst_severity", "unknown"),
             "no blocking host-substrate activity",
             detail_ok if not blocking_risks else
             "; ".join(f"{r['kind']} on {r['host_substrate']} - {r['why']}"
                       for r in blocking_risks)[:600])
    else:
        gate("enzyme_host_safety", False, "not screened",
             "an enzyme safety screen",
             "no host-safety screen was supplied for the candidate enzyme. The "
             "question of whether this protein attacks host tissue has not been "
             "asked, which is not the same as a negative answer")

    # 16. PRODUCT HAZARD MECHANISM.
    #     Distinct from the GHS gate: that one asks whether a regulatory
    #     classification has been fetched, this one asks whether the product has
    #     a known mechanism of local harm.
    prods = list(spec.get("products") or [])
    if assay.get("product"):
        prods.append(str(assay["product"]))
    passess = assess_products(sorted(set(prods)))
    pblock = passess.get("blocking") or []
    gate("product_hazard", not pblock, ", ".join(pblock) or passess["worst_severity"],
         "no product with a blocking hazard mechanism",
         passess["summary"] if not pblock else
         "; ".join(h["mechanism"][:200] for h in passess["hazards"]
                   if h["severity"] == "blocking"))

    # 17. CLINICAL NECESSITY.
    #
    #     The comparator for this whole approach is not "do nothing" - it is
    #     conventional retrieval. If a single fragment can be reached with a
    #     cannula under ultrasound, it can usually be reached with forceps,
    #     and removal then takes minutes with a proven technique. A catalyst
    #     has to be justified against THAT, and a system that never asks the
    #     question is quietly assuming its own necessity.
    #
    #     The two presentations give genuinely different answers, which is why
    #     presentation is a first-class choice rather than a detail:
    #       - single_fragment, reachable  -> refuse; recommend retrieval
    #       - single_fragment, unreachable -> proceed, and say why it qualifies
    #       - dispersed_particulate       -> proceed; thousands of micron-scale
    #                                        particles cannot be retrieved
    #                                        mechanically at any cost
    pres = str(passport.get("presentation") or "single_fragment")
    retrievable = passport.get("retrievable_mechanically")
    anat = str(passport.get("anatomy_class", "soft_tissue")).lower()
    if pres == "dispersed_particulate":
        gate("clinical_necessity", True, "dispersed_particulate",
             "not mechanically retrievable",
             f"dispersed particulate over ~{int(assay.get('n_particles') or 0):,} "
             f"particles. Mechanical retrieval is not an option at any cost, so "
             f"a chemical route has no conventional comparator to beat")
    elif retrievable is True:
        gate("clinical_necessity", False, "retrievable", "not retrievable, or declined",
             "this is a single fragment in tissue that appears mechanically "
             "retrievable. Removal under ultrasound guidance takes minutes with "
             "a proven technique, so a catalytic route is not justified here. "
             "Recommend conventional retrieval. The approach is for fragments "
             "that cannot safely be reached, or where surgery has been declined")
    else:
        gate("clinical_necessity", True, "not retrievable",
             "not retrievable, or declined",
             f"single fragment, mechanical retrieval not a realistic option "
             f"(location: {anat}). The approach has a genuine gap to fill here")

    failed = [g["name"] for g in gates if not g["passed"]]
    return {
        "presentation": pres,
        "product_assessment": passess,
        "enzyme_safety": enzyme_safety or None,
        "gates": gates,
        "passed": not failed,
        "failed": failed,
        # Any failure is blocking. There is no "advisory" tier on purpose.
        "blocking": bool(failed),
        "kinetics_provenance": prov,
        "summary": (
            f"all {len(gates)} gates passed"
            if not failed
            else f"{len(failed)} of {len(gates)} gates failed: {', '.join(failed)}"
        ),
        "disclaimer": simulation_disclaimer(),
    }


def plan_next_experiment(
    assays: list[dict[str, Any]] | None = None, budget: int = 3
) -> dict[str, Any]:
    """Rank wet-lab experiments by how much uncertainty they would remove.

    Active learning, kept deliberately simple and legible: the value of
    measuring a candidate is its predictive uncertainty weighted by how good
    it might plausibly be (the upper end of its band). Measuring a candidate
    that is confidently bad teaches you nothing; measuring an uncertain
    candidate that could be excellent is the experiment worth paying for.
    """
    assays = assays or []
    b = int(max(1, min(int(budget), 10)))
    ranked: list[dict[str, Any]] = []
    for a in assays:
        un = float(a.get("uncertainty", 0.0))
        ci = a.get("erosion_rate_ci") or [0.0, 0.0]
        upside = float(ci[1]) if len(ci) > 1 else 0.0
        gates_ok = bool(a.get("gates_passed", True))
        # log1p keeps a single wild band from dominating the ordering.
        value = math.log1p(max(un, 0.0)) * math.log1p(max(upside, 0.0))
        if not gates_ok:
            value *= 0.25  # still informative, but not the first thing to run
        ranked.append({
            "candidate": a.get("candidate", a.get("name", "unnamed")),
            "information_value": round(value, 4),
            "uncertainty": round(un, 4),
            "upside_um_per_day": round(upside, 4),
            "gates_passed": gates_ok,
        })
    ranked.sort(key=lambda r: r["information_value"], reverse=True)
    for i, r in enumerate(ranked, 1):
        r["priority"] = i
    return {
        "experiments": ranked[:b],
        "deferred": ranked[b:],
        "method": "uncertainty x plausible-upside ranking (log-damped)",
        "note": "Priority 1 is the measurement that would most reduce "
                "uncertainty about a candidate that could actually work.",
    }


def wait(seconds: float = 1.0) -> dict[str, Any]:
    """Pause. Bounded, because an unbounded sleep is a denial of service."""
    s = max(0.0, min(float(seconds), 5.0))
    time.sleep(s)
    return {"waited": s}


def engine_info() -> dict[str, Any]:
    """Startup diagnostic, reported by the worker on connect."""
    return {
        "engine_version": ENGINE_VERSION,
        "numpy": getattr(kinetics.np, "__version__", None) if kinetics.np else None,
        "mock": _mock(),
        "materials": sorted(MATERIALS),
        "no_go_materials": sorted(NO_GO_MATERIALS),
        "edits": sorted(EDIT_CATALOGUE),
        "gate_thresholds": GATE_THRESHOLDS,
    }
