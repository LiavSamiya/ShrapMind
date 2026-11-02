"""Wire and storage types shared by the engine, the DB layer and the API.

Same role as voodo's shared/protocol.py. Where voodo carries a solution and
the steps that fixed a machine, this carries a proposed catalyst and the gaps
that stand between it and working in tissue.

One field deserves its own note. `substrate_class` travels with every
proposal, because the single most important fact about this corpus is that of
289 catalytic constants, none was measured on a solid polymer. A proposal that
arrives at a reviewer without that attached invites them to read a kcat from a
chromogenic ester as if it described a fragment, which is the exact error the
engine was built to make impossible.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EvidenceLevel = Literal[
    "experimental", "curated", "predicted", "assumed", "expert_review"
]
SubstrateClass = Literal["polymer", "oligomer", "model", "unknown"]
Verdict = Literal[
    "agree", "disagree", "unconvinced", "needs_experiment", "out_of_scope"
]
ChangeType = Literal["add", "delete", "amend"]
ChangeStatus = Literal["pending", "approved", "rejected"]


class Gap(BaseModel):
    """A named distance between what was measured and what the body requires."""

    kind: str
    detail: str
    measured: str | None = None
    target: str | None = None
    action: str | None = None
    pmid: str | None = None


class ProposalRecord(BaseModel):
    """A catalyst the engine proposed for a case."""

    id: str | None = None
    problem_summary: str
    material: str
    enzyme_name: str | None = None
    uniprot_accession: str | None = None
    score: float | None = None
    rationale: str | None = None
    gaps: list[Gap] = Field(default_factory=list)
    evidence_level: EvidenceLevel = "curated"
    substrate_class: SubstrateClass | None = None


class ProposalMatch(BaseModel):
    """A stored proposal and how close it is to the case being asked about."""

    record: ProposalRecord
    score: float


class PendingChange(BaseModel):
    """An assertion waiting for a biologist.

    Nothing reaches `proposals` except through an approval here.
    """

    id: str | None = None
    type: ChangeType = "add"
    proposal_id: str | None = None
    problem_summary: str
    material: str | None = None
    enzyme_name: str | None = None
    rationale: str | None = None
    gaps: list[Gap] = Field(default_factory=list)
    reason: str
    submitted_by: str = "engine"
    status: ChangeStatus = "pending"
    verdict: Verdict | None = None
    confidence: int | None = Field(default=None, ge=1, le=5)
    reviewer: str | None = None
    reviewer_note: str | None = None
    cites_pmid: list[str] = Field(default_factory=list)
    created_at: str | None = None
    reviewed_at: str | None = None


class ReviewDecision(BaseModel):
    """What a reviewer submits when they answer a queued item."""

    verdict: Verdict
    reviewer: str
    note: str
    confidence: int | None = Field(default=None, ge=1, le=5)
    cites_pmid: list[str] = Field(default_factory=list)
