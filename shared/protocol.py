"""Wire types shared between the backend (server/) and the simulation
worker (client/worker/). This module is the protocol contract for
WebSocket payloads - changing it forces both sides to be redeployed.

Nothing in here describes a treatment. A FragmentPassport is a material
record, a ReactionSpec is a chemistry target, an AssayResult is the output
of a numerical model. Every candidate this system emits is a simulation
hypothesis that requires wet-lab validation.
"""
from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

# The agent's vocabulary. Single source of truth: server/agent/tools.py
# enforces an allow-list against these names, client/worker/engines.py
# implements one function per worker-side name, and server/agent/bench.py
# exposes one method per name. Keep all four in sync.
ToolName = Literal[
    # inspect
    "read_passport",
    "characterize_fragment",
    "define_reaction",
    "get_material_notes",
    # design
    "retrieve_enzymes",
    "retrieve_precedents",
    "propose_variants",
    "predict_properties",
    # validate
    "score_kinetics",
    "simulate_hydrogel_assay",
    "check_mass_balance",
    "run_safety_gates",
    # decide
    "rank_candidates",
    "plan_next_experiment",
    "highlight_step",
    "submit_candidate",
    "wait",
    "finish",
]

# The event stream is a typed `kind` over an untyped `payload` dict; the UI
# switches on kind and reads the payload loosely. `mode_change` is declared
# here on purpose - VooDo emits it without declaring it, which a pydantic
# Literal would reject.
EventKind = Literal[
    "thought",
    "thought_delta",
    "tool_call",
    "observation",
    "result",
    "error",
    "status",
    "mode_change",
    "stage",
]

# The ten pipeline stages the UI strip renders, in order.
Stage = Literal[
    "inspect",
    "characterize",
    "reaction",
    "retrieve",
    "generate",
    "predict",
    "simulate",
    "gate",
    "rank",
    "report",
]

Mode = Literal["run", "explain"]

# How the material presents in the tissue. This is a first-class choice, not a
# detail, because it changes which problem is being solved.
#
#   single_fragment      one macroscopic object. Removable with forceps if it
#                        can be reached, so the case for a catalyst rests
#                        entirely on it being unreachable or unsafe to reach.
#   dispersed_particulate  thousands of micron-scale particles through a tissue
#                        volume - blast micro-shrapnel, implant wear debris,
#                        metallosis. Not retrievable mechanically at any cost,
#                        and the surface-area-to-volume ratio is orders of
#                        magnitude higher, which is what makes the chemistry
#                        tractable.
Presentation = Literal["single_fragment", "dispersed_particulate"]


class CaseMessage(BaseModel):
    """app -> agent. The user's description of the fragment case."""

    text: str
    attachments: list[str] = Field(default_factory=list)  # base64 instrument exports
    mode: Mode = "run"
    # An explicit presentation from the console. None means "infer it from the
    # case text, and say that it was inferred".
    presentation: Presentation | None = None


class ToolCall(BaseModel):
    name: ToolName
    args: dict[str, Any] = Field(default_factory=dict)


class AgentEvent(BaseModel):
    kind: EventKind
    payload: dict[str, Any] = Field(default_factory=dict)
    ts: float = Field(default_factory=time.time)


class FragmentPassport(BaseModel):
    """What the material is made of, how it presents, and where it sits.

    `confidence` matters: a passport inferred from imaging alone is weaker
    evidence than one from a physical sample, and the agent is told to say so.

    `presentation` matters more. A single macroscopic fragment and a cloud of
    micron-scale particles are the same chemistry and two different
    engineering problems: surface area differs by orders of magnitude, the
    clinical justification is not the same argument, and in the dispersed case
    the right answer may not involve an enzyme at all.
    """

    material_family: str  # pet | pa | pla | iron_steel | cellulose | ... | unknown
    presentation: Presentation = "single_fragment"
    surface_state: str = "unknown"  # oxidised | coated | crystalline | pristine
    additives: list[str] = Field(default_factory=list)
    anatomy_class: str = "soft_tissue"  # soft_tissue | peri_articular | near_nerve
    volume_mm3: float | None = None
    # Dispersed presentation only: the particle size distribution's centre,
    # and how many particles that implies for the stated total volume.
    particle_size_um: float | None = None
    particle_count: int | None = None
    # Whether conventional retrieval is a realistic alternative. The honest
    # comparator for this entire approach, and what the clinical-necessity
    # gate turns on.
    retrievable_mechanically: bool | None = None
    confidence: float = 0.0  # 0..1
    source: str = "unspecified"  # sample | imaging | assumed


class ReactionSpec(BaseModel):
    """The chemistry target: what bond to attack and what must not be produced."""

    bond_class: str
    mechanism: Literal["hydrolysis", "redox", "chelation"]
    products: list[str] = Field(default_factory=list)
    cofactors: list[str] = Field(default_factory=list)
    forbidden_products: list[str] = Field(default_factory=list)
    notes: str = ""


class EnzymeCandidate(BaseModel):
    """An in-silico proposal. `provenance` is never allowed to claim more."""

    name: str
    parent_family: str
    edits: list[str] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)
    provenance: str = "in-silico proposal"


class GateResult(BaseModel):
    """One safety gate. Always carries the number that decided it."""

    name: str
    passed: bool
    value: float | None = None
    threshold: float | None = None
    detail: str = ""


class AssayResult(BaseModel):
    """Output of the numerical hydrogel assay. Not a measurement."""

    candidate: str
    conditions: dict[str, Any] = Field(default_factory=dict)
    timeseries: list[dict[str, float]] = Field(default_factory=list)
    erosion_rate_um_per_day: float = 0.0
    erosion_rate_ci: tuple[float, float] | None = None
    mass_balance_residual: float = 0.0
    captured_fraction: float = 0.0
    gates: list[GateResult] = Field(default_factory=list)

    @property
    def gates_passed(self) -> bool:
        return all(g.passed for g in self.gates) and bool(self.gates)


class DesignStep(BaseModel):
    action: ToolCall
    note: str | None = None


class DesignRun(BaseModel):
    """A complete design loop, persisted and semantically searchable."""

    id: str | None = None
    case_summary: str
    passport: FragmentPassport | None = None
    reaction_spec: ReactionSpec | None = None
    steps: list[DesignStep] = Field(default_factory=list)
    chosen_candidate: EnzymeCandidate | None = None
    assay: AssayResult | None = None
    success: bool = False
    embedding: list[float] | None = None


class RunMatch(BaseModel):
    record: DesignRun
    score: float


class FamilyMatch(BaseModel):
    """An enzyme family retrieved from the knowledge base."""

    name: str
    ec_class: str
    reaction_class: str
    substrate_material: str
    kinetics: dict[str, Any] = Field(default_factory=dict)
    conditions: dict[str, Any] = Field(default_factory=dict)
    source: str = ""
    score: float = 0.0


class PrecedentMatch(BaseModel):
    """A literature precedent, with both halves of the claim.

    `what_it_does_not_prove` is not decoration - it is the column that keeps
    the pitch honest, and the agent is required to carry it through to the
    final report.
    """

    title: str
    claim: str
    what_it_proves: str
    what_it_does_not_prove: str
    citation: str
    score: float = 0.0
