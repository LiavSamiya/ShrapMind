"""The bridge from f2c's evidence warehouse to the simulator's inputs.

This is where the two halves of the project meet, and the whole point of it is
to make sure nothing crosses the join without its provenance.

WHY THIS MODULE EXISTS
    f2c holds 505 experimentally-verified enzymes with 420 condition-bearing
    observations and a citation on every number. The simulator needs a handful
    of scalars: k_cat, K_m, a temperature optimum, a half-life. Flattening the
    former into the latter is lossy in a way that matters, because of one fact:

        NOT ONE k_cat IN THE WAREHOUSE WAS MEASURED ON A SOLID POLYMER.

    Of 289 kinetic measurements, 168 are on chromogenic model esters
    (4-nitrophenyl acetate and friends), 42 on soluble oligomers, 58 unrecorded.
    f2c's own test asserts this and calls a future failure of that test "good
    news". So a k_cat handed to a surface-erosion model is, today, always a
    constant measured on something other than the thing being eroded.

    This module therefore returns kinetics *and* the substrate class they were
    measured on, so the simulator can widen its uncertainty accordingly and the
    gate battery can refuse a confident rate claim. See
    client/worker/kinetics.py (provenance-scaled sigma) and
    engines.run_safety_gates (the kinetics_provenance gate).

REUSE, NOT REWRITE
    Every piece of f2c's logic that already does this correctly is imported
    rather than reimplemented: warehouse.load for the on-disk format,
    substrate.classify for the proxy-substrate question, and the median-with-
    spread summarising idea from rank._summarise (which cites the measurement
    closest to the median so the number shown and the paper cited agree).

NO DATABASE REQUIRED
    This reads the committed warehouse.json directly and indexes it in memory.
    That is deliberate: it means real evidence is available even with SKIP_DB,
    so the demo path and the test suite both run on real data rather than on
    placeholders. Postgres remains the path for semantic search at scale.
"""
from __future__ import annotations

import functools
import logging
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shared.biosafety import assess_enzyme

log = logging.getLogger("shrapmind.evidence")

# f2c lives at the repo root alongside server/ and client/.
try:
    from f2c import substrate, warehouse
    from f2c.retrieve import ALIASES, NON_ENZYMATIC
    from f2c.schema import Protein
    _F2C = True
except ImportError:  # pragma: no cover - f2c is vendored, but stay honest
    substrate = warehouse = None  # type: ignore[assignment]
    ALIASES, NON_ENZYMATIC = {}, {}  # type: ignore[assignment]
    Protein = Any  # type: ignore[assignment,misc]
    _F2C = False

# How much to believe a constant, given what it was measured on. These are
# f2c's own weights; the simulator turns them into uncertainty instead of score.
PROVENANCE_SIGMA = {
    "polymer": 0.25,   # measured on the real material - the band we would like
    "oligomer": 0.50,  # soluble fragment of it
    "model": 0.90,     # a chromogenic stand-in; spans roughly an order of magnitude
    "unknown": 1.20,   # substrate not recorded at all
}

_KINETIC_METRICS = ("kcat", "km", "kcat_km", "specific_activity")


@dataclass
class Measured:
    """One summarised metric, carrying how it was measured and by whom."""

    metric: str
    value: float
    unit: str | None
    n: int
    spread: float
    substrate_class: str
    substrate_name: str | None
    citation: str | None
    pmid: str | None
    doi: str | None
    source_db: str
    source_version: str | None
    retrieved_at: str | None
    assay_temperature_c: float | None = None
    assay_ph: float | None = None

    def describe(self) -> str:
        base = (f"{self.value:g} {self.unit or ''}".strip() if self.n == 1
                else f"median {self.value:g} {self.unit or ''} over {self.n} "
                     f"measurements (range {self.spread:g})".strip())
        on = f" on {self.substrate_name}" if self.substrate_name else ""
        cite = f" [{self.citation}]" if self.citation else ""
        return base + on + cite


@dataclass
class EnzymeEvidence:
    """What the warehouse knows about one candidate enzyme family."""

    name: str
    protein_id: str
    uniprot_accession: str | None
    organism: str
    ec_numbers: list[str]
    reviewed: bool | None
    pdb_ids: list[str]
    rhea_ids: list[str]
    chebi_ids: list[str]
    catalytic_reactions: list[str]
    substrate_abbreviations: list[str]
    publication_count: int
    measured: dict[str, Measured] = field(default_factory=dict)
    # The weakest-link provenance across the kinetic constants, which is what
    # the simulator and the gate are judged on.
    kinetics_provenance: str = "unknown"
    # Parameters the simulator needs but nobody measured.
    missing: list[str] = field(default_factory=list)
    retrieved_at: str | None = None
    source_version: str | None = None
    # Host-safety screen: does this protein attack the patient? Attached here
    # so it travels with the candidate rather than being an optional extra
    # step the agent might skip.
    safety: Any = None

    # ------------------------------------------------------------------ export

    def to_base_params(self) -> dict[str, Any]:
        """The scalars the kinetic model consumes.

        Only measured values are included. A parameter nobody measured is
        LEFT OUT rather than defaulted, so the simulator has to notice it is
        missing instead of silently substituting a plausible-looking number.
        """
        out: dict[str, Any] = {}
        if "kcat" in self.measured:
            out["k_cat"] = self.measured["kcat"].value
        if "km" in self.measured:
            km = self.measured["km"]
            # BRENDA and UniProt report K_m in mM; the model wants uM.
            out["k_m_uM"] = km.value * 1000.0 if (km.unit or "").lower() == "mm" else km.value
        if "temperature_optimum_c" in self.measured:
            out["t_opt_c"] = self.measured["temperature_optimum_c"].value
        if "ph_optimum" in self.measured:
            out["ph_opt"] = self.measured["ph_optimum"].value
        if "half_life_h" in self.measured:
            out["half_life_h"] = self.measured["half_life_h"].value
        out["kinetics_provenance"] = self.kinetics_provenance
        out["assumed_parameters"] = list(self.missing)
        if self.safety is not None:
            out["enzyme_safety"] = self.safety.to_dict()
        out["evidence_citations"] = [
            m.citation for m in self.measured.values() if m.citation
        ]
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "protein_id": self.protein_id,
            "uniprot_accession": self.uniprot_accession,
            "organism": self.organism,
            "ec_numbers": self.ec_numbers,
            "reviewed": self.reviewed,
            "pdb_ids": self.pdb_ids[:5],
            "rhea_ids": self.rhea_ids[:5],
            "chebi_ids": self.chebi_ids[:10],
            "catalytic_reactions": self.catalytic_reactions[:2],
            "substrate_abbreviations": self.substrate_abbreviations,
            "publication_count": self.publication_count,
            "kinetics_provenance": self.kinetics_provenance,
            "measured": {k: v.describe() for k, v in self.measured.items()},
            "missing": self.missing,
            "enzyme_safety": self.safety.to_dict() if self.safety else None,
            "retrieved_at": self.retrieved_at,
            "source_version": self.source_version,
        }


def _summarise(protein: Any, metric: str) -> Measured | None:
    """Median of every measured value for a metric, with its spread.

    The median rather than the first value (which would make the answer depend
    on ingest order) or the nearest to body conditions (which would be
    cherry-picking). The citation attached is the measurement closest to the
    median, so the number shown and the paper credited for it agree - f2c's
    rule, kept.
    """
    measured = [o for o in protein.observations_for(metric) if o.value is not None]
    if not measured:
        return None
    values = sorted(float(o.value) for o in measured)
    median = statistics.median(values)
    closest = min(measured, key=lambda o: abs(float(o.value) - median))
    conds = closest.conditions or {}
    sub_name = conds.get("substrate")
    ev = closest.evidence
    return Measured(
        metric=metric,
        value=median,
        unit=closest.unit,
        n=len(measured),
        spread=values[-1] - values[0],
        substrate_class=substrate.classify(sub_name) if _F2C else "unknown",
        substrate_name=sub_name,
        citation=ev.citation() if hasattr(ev, "citation") else None,
        pmid=getattr(ev, "pmid", None),
        doi=getattr(ev, "doi", None),
        source_db=getattr(ev, "source_db", ""),
        source_version=getattr(ev, "source_version", None),
        retrieved_at=getattr(ev, "retrieved_at", None),
        assay_temperature_c=conds.get("assay_temperature_c"),
        assay_ph=conds.get("assay_ph"),
    )


def _build(protein: Any) -> EnzymeEvidence:
    ev = EnzymeEvidence(
        name=protein.name,
        protein_id=protein.protein_id,
        uniprot_accession=protein.uniprot_accession,
        organism=protein.organism,
        ec_numbers=list(protein.ec_numbers or []),
        reviewed=protein.reviewed,
        pdb_ids=list(protein.pdb_ids or []),
        rhea_ids=list(protein.rhea_ids or []),
        chebi_ids=list(protein.chebi_ids or []),
        catalytic_reactions=list(protein.catalytic_reactions or []),
        substrate_abbreviations=sorted({
            (s.get("abbreviation") or "").upper()
            for s in (protein.substrates or []) if s.get("abbreviation")
        }),
        publication_count=protein.publication_count(),
    )
    for metric in (*_KINETIC_METRICS, "temperature_optimum_c", "ph_optimum", "half_life_h"):
        m = _summarise(protein, metric)
        if m is not None:
            ev.measured[metric] = m

    # Weakest link across the kinetic constants: if any constant the model will
    # use came from a chromogenic stand-in, the whole prediction inherits that.
    classes = [m.substrate_class for k, m in ev.measured.items() if k in _KINETIC_METRICS]
    ev.kinetics_provenance = (
        _weakest(classes) if classes else "unknown"
    )

    for needed, label in (("kcat", "k_cat"), ("km", "K_m"),
                          ("half_life_h", "half_life"),
                          ("temperature_optimum_c", "temperature_optimum"),
                          ("ph_optimum", "pH_optimum")):
        if needed not in ev.measured:
            ev.missing.append(label)

    t_opt = ev.measured.get("temperature_optimum_c")
    ev.safety = assess_enzyme(
        ev.name, ev.ec_numbers, ev.organism,
        t_opt.value if t_opt else None)

    first = next(iter(ev.measured.values()), None)
    if first is not None:
        ev.retrieved_at = first.retrieved_at
        ev.source_version = first.source_version
    return ev


def _weakest(classes: list[str]) -> str:
    """The least trustworthy class present. The opposite of substrate.best():
    f2c scores on the strongest evidence available, but a SIMULATION must be
    judged on its weakest input, because that is what bounds the result."""
    order = ["unknown", "model", "oligomer", "polymer"]
    present = [c for c in order if c in classes]
    return present[0] if present else "unknown"


class EvidenceIndex:
    """In-memory index over the warehouse. Built once, queried many times."""

    def __init__(self, proteins: list[Any], built_at: str | None = None) -> None:
        self.built_at = built_at
        self.records: list[EnzymeEvidence] = [_build(p) for p in proteins]
        self.by_material: dict[str, list[EnzymeEvidence]] = {}
        for rec in self.records:
            for abbr in rec.substrate_abbreviations:
                self.by_material.setdefault(abbr, []).append(rec)
        # Strongest evidence first: real material, then more papers.
        rank = {"polymer": 3, "oligomer": 2, "model": 1, "unknown": 0}
        for abbr in self.by_material:
            # A candidate that would attack host tissue is never ranked above
            # one that would not, whatever its kinetics - the same rule the
            # gate battery applies, applied at retrieval so the agent sees the
            # safe options first.
            self.by_material[abbr].sort(
                key=lambda r: (0 if (r.safety and r.safety.blocking) else 1,
                               rank.get(r.kinetics_provenance, 0),
                               r.publication_count,
                               len(r.measured)),
                reverse=True)

    # ------------------------------------------------------------------ query

    def normalise(self, material: str) -> str:
        """Map a free-text material name onto a warehouse abbreviation,
        reusing f2c's alias table."""
        s = (material or "").strip().lower()
        return ALIASES.get(s, s.upper())

    def blocked_reason(self, material: str) -> str | None:
        """f2c's non-enzymatic objection for this material, if it has one."""
        return NON_ENZYMATIC.get((material or "").strip().lower())

    def for_material(self, material: str, top_k: int = 5) -> list[EnzymeEvidence]:
        return self.by_material.get(self.normalise(material), [])[:max(1, int(top_k))]

    def search(self, query: str, material: str | None = None,
               top_k: int = 5) -> list[EnzymeEvidence]:
        """Find candidate enzymes.

        With a material named, results are ordered by EVIDENCE QUALITY:
        host-safe first, then by what the kinetics were measured on, then by
        whether a turnover number exists at all, then by replication. With no
        material, keyword overlap leads.

        Deliberately transparent rather than embedding-based. The semantic
        index lives in Postgres; this is the offline path, and a ranking a
        reviewer can read is easier to defend than one nobody can inspect.
        """
        if material:
            pool = self.for_material(material, top_k=10_000)
            if not pool:
                return []
        else:
            pool = self.records
        terms = [t for t in (query or "").lower().split() if len(t) > 2]

        def hits(rec: EnzymeEvidence) -> int:
            hay = " ".join([
                rec.name.lower(), " ".join(rec.ec_numbers).lower(),
                " ".join(rec.catalytic_reactions).lower(),
                " ".join(rec.substrate_abbreviations).lower(),
                rec.organism.lower(),
            ])
            return sum(1 for t in terms if t in hay)

        prov_rank = {"polymer": 3, "oligomer": 2, "model": 1, "unknown": 0}

        def quality(rec: EnzymeEvidence) -> tuple:
            return (
                # Never rank a host-unsafe candidate above a safe one.
                0 if (rec.safety and rec.safety.blocking) else 1,
                prov_rank.get(rec.kinetics_provenance, 0),
                1 if "kcat" in rec.measured else 0,
                rec.publication_count,
                len(rec.measured),
            )

        # EVIDENCE QUALITY OUTRANKS KEYWORD MATCH once a material is named.
        #
        # This was the other way round, and it actively excluded the best
        # records in the warehouse. NylB and NylC are the only enzymes here
        # with a turnover number measured on a genuine oligomer of their own
        # target - the strongest kinetic evidence in the entire dataset - but
        # the words "amide" and "hydrolysis" appear nowhere in their name, EC
        # string or reaction text, so a keyword-first ranking buried them
        # beneath esterases that merely mentioned the right words. Once the
        # caller has named the material, the chemistry is already constrained
        # and keyword overlap adds little while being able to do real harm.
        if material:
            return sorted(pool, key=quality, reverse=True)[:max(1, int(top_k))]

        # With no material filter the keyword IS the query, so it leads.
        if not terms:
            return pool[:max(1, int(top_k))]
        scored = sorted(pool, key=lambda r: (hits(r), quality(r)), reverse=True)
        matched = [r for r in scored if hits(r) > 0]
        return (matched or scored)[:max(1, int(top_k))]

    def coverage(self) -> dict[str, Any]:
        """What the knowledge base does and does not cover - used by /health
        and shown in the console, because a user is entitled to know that a
        material has no evidence behind it before reading a recommendation."""
        prov: dict[str, int] = {}
        for r in self.records:
            prov[r.kinetics_provenance] = prov.get(r.kinetics_provenance, 0) + 1
        return {
            "built_at": self.built_at,
            "proteins": len(self.records),
            "materials": {k: len(v) for k, v in sorted(self.by_material.items())},
            "kinetics_provenance": prov,
            "with_kcat": sum(1 for r in self.records if "kcat" in r.measured),
            "with_half_life": sum(1 for r in self.records if "half_life_h" in r.measured),
            "polymer_level_kinetics": prov.get("polymer", 0),
            "host_unsafe": sum(1 for r in self.records
                               if r.safety and r.safety.blocking),
        }


@functools.lru_cache(maxsize=1)
def index(store: str | None = None) -> EvidenceIndex:
    """Load and index the warehouse once per process."""
    if not _F2C:
        raise RuntimeError("f2c package not importable - the evidence layer is unavailable")
    path = Path(store) if store else warehouse.DEFAULT_STORE
    proteins = warehouse.load(path)
    built_at = None
    try:
        import json

        built_at = json.loads(Path(path).read_text()).get("built_at")
    except Exception:  # noqa: BLE001
        pass
    idx = EvidenceIndex(proteins, built_at=built_at)
    log.info("evidence index: %d proteins, %d materials",
             len(idx.records), len(idx.by_material))
    return idx
