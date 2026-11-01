"""Shared wire types and config. Both the backend and the simulation worker
depend on this package; touch with care.

Note: internal modules import from the submodules directly
(`from shared.config import settings`), never through this barrel. The barrel
documents the public surface.
"""
from shared.config import Settings, settings
from shared.protocol import (
    AgentEvent,
    AssayResult,
    CaseMessage,
    DesignRun,
    DesignStep,
    EnzymeCandidate,
    EventKind,
    FamilyMatch,
    FragmentPassport,
    GateResult,
    Mode,
    PrecedentMatch,
    ReactionSpec,
    RunMatch,
    Stage,
    ToolCall,
    ToolName,
)
from shared.safety import (
    ClinicalOutputRefused,
    ParameterOutOfRange,
    cap_case_message,
    check_clinical_output,
    sanitize_for_prompt,
    simulation_disclaimer,
    validate_number,
)

__all__ = [
    "AgentEvent", "AssayResult", "CaseMessage", "DesignRun", "DesignStep",
    "EnzymeCandidate", "EventKind", "FamilyMatch", "FragmentPassport",
    "GateResult", "Mode", "PrecedentMatch", "ReactionSpec", "RunMatch",
    "Stage", "ToolCall", "ToolName",
    "Settings", "settings",
    "ClinicalOutputRefused", "ParameterOutOfRange", "cap_case_message",
    "check_clinical_output", "sanitize_for_prompt", "simulation_disclaimer",
    "validate_number",
]
