"""Canonical entities for Fragment-to-Catalyst.

Design rule enforced throughout: a number never travels without its evidence.
Every measured quantity is an Observation carrying the database, the release it
came from and the publication that reported it. Values we could not source are
absent, never guessed -- `None` means "not measured", which is different from
"measured and found to be zero".
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal

EvidenceLevel = Literal["experimental", "curated", "predicted", "assumed"]

# Physiological reference point for deep skeletal muscle.
BODY_TEMPERATURE_C = 37.0
BODY_PH = 7.4


@dataclass(frozen=True)
class Evidence:
    """Where a single fact came from."""

    source_db: str
    retrieved_at: str
    level: EvidenceLevel
    pmid: str | None = None
    doi: str | None = None
    source_version: str | None = None

    def citation(self) -> str:
        if self.pmid:
            return f"PMID:{self.pmid}"
        if self.doi:
            return self.doi
        return self.source_db


@dataclass(frozen=True)
class Observation:
    """A measured value plus the conditions it was measured under.

    `conditions` is deliberately free-form: assay context differs between
    databases and flattening it would destroy the thing that makes the value
    comparable (or not) to another one.
    """

    metric: str
    value: float | None
    unit: str | None
    evidence: Evidence
    conditions: dict[str, Any] = field(default_factory=dict)
    note: str | None = None


@dataclass
class Protein:
    """A candidate catalyst as assembled from the source databases."""

    protein_id: str
    name: str
    sequence: str
    sequence_md5: str
    organism: str
    taxon_id: int | None
    substrates: list[dict[str, Any]]
    uniprot_accession: str | None
    evidence: list[Evidence]
    literature: list[dict[str, Any]] = field(default_factory=list)
    pdb_ids: list[str] = field(default_factory=list)
    alphafold_url: str | None = None

    # Filled in by the UniProt enrichment pass; absent when not annotated.
    reviewed: bool | None = None
    ec_numbers: list[str] = field(default_factory=list)
    rhea_ids: list[str] = field(default_factory=list)
    chebi_ids: list[str] = field(default_factory=list)
    catalytic_reactions: list[str] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)

    def observations_for(self, metric: str) -> list[Observation]:
        return [o for o in self.observations if o.metric == metric]

    def publication_count(self) -> int:
        """Distinct publications reporting this protein's activity."""
        keys = {
            (lit.get("doi") or lit.get("title") or "").strip().lower()
            for lit in self.literature
        }
        keys.discard("")
        return len(keys)


@dataclass
class MaterialSpec:
    """The fragment as characterised -- layer 0, the shrapnel passport.

    A polymer is not a small molecule: form, crystallinity and particle size
    change whether an enzyme can act at all, so they are first-class fields
    rather than free text.
    """

    polymer: str
    form: str = "polymer"  # polymer | oligomer | film | fibre | powder
    mass_mg: float | None = None
    crystallinity_pct: float | None = None
    particle_size_mm: float | None = None
    surface_treatment: str | None = None
    site: str = "deep_muscle"
    protein_corona: bool = True

    def is_polymeric(self) -> bool:
        return self.form != "oligomer"


@dataclass
class Gap:
    """A specific reason the natural enzyme does not fit body conditions.

    This is the hand-off to the protein-engineering layer: each gap names the
    measured value, the target, and which property has to be engineered.
    """

    kind: str
    detail: str
    measured: str | None
    target: str
    engineering_target: str
    evidence: Evidence | None = None


@dataclass
class ScoredCandidate:
    protein: Protein
    score: float
    uncertainty: float
    reasons: list[str]
    unknowns: list[str]
    gaps: list[Gap] = field(default_factory=list)


@dataclass
class Decision:
    """What the product returns."""

    material: MaterialSpec
    verdict: str  # enzyme_selected | no_pathway | no_candidate_meets_bar
    selected: ScoredCandidate | None
    alternatives: list[ScoredCandidate]
    rationale: str
    capture: dict[str, Any] | None = None
    generated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
