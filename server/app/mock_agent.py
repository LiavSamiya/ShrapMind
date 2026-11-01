"""A canned event sequence, so the console can be exercised with no worker,
no database and no API key. Matches run_design's signature shape."""
from __future__ import annotations

import time
from collections.abc import Callable

from shared.protocol import AgentEvent, CaseMessage

EmitFn = Callable[[AgentEvent], None]

_SCRIPT: list[tuple[float, str, dict]] = [
    (0.2, "status", {"msg": "Reading the case..."}),
    (0.3, "stage", {"stage": "characterize", "tool": "characterize_fragment"}),
    (0.1, "thought", {"text": "Working out what the fragment is made of first - "
                              "every downstream choice depends on it."}),
    (0.4, "tool_call", {"name": "characterize_fragment", "stage": "characterize"}),
    (0.3, "observation", {"name": "characterize_fragment",
                          "result": {"passport": {"material_family": "cellulose",
                                                  "confidence": 0.75,
                                                  "source": "assumed"}}}),
    (0.2, "stage", {"stage": "reaction", "tool": "define_reaction"}),
    (0.3, "tool_call", {"name": "define_reaction", "stage": "reaction"}),
    (0.2, "stage", {"stage": "retrieve", "tool": "retrieve_enzymes"}),
    (0.3, "tool_call", {"name": "retrieve_enzymes", "stage": "retrieve"}),
    (0.2, "stage", {"stage": "generate", "tool": "propose_variants"}),
    (0.3, "tool_call", {"name": "propose_variants", "stage": "generate"}),
    (0.2, "stage", {"stage": "simulate", "tool": "simulate_hydrogel_assay"}),
    (0.6, "tool_call", {"name": "simulate_hydrogel_assay", "stage": "simulate"}),
    (0.3, "observation", {"name": "simulate_hydrogel_assay",
                          "result": {"candidate": "cellulase-WT",
                                     "erosion_rate_um_per_day": 113.1,
                                     "erosion_rate_ci": [43.6, 360.2],
                                     "captured_fraction": 0.77}}),
    (0.2, "stage", {"stage": "gate", "tool": "run_safety_gates"}),
    (0.4, "tool_call", {"name": "run_safety_gates", "stage": "gate"}),
    (0.2, "stage", {"stage": "rank", "tool": "rank_candidates"}),
    (0.3, "tool_call", {"name": "rank_candidates", "stage": "rank"}),
    (0.2, "stage", {"stage": "report", "tool": "finish"}),
]


def run_mock_design(message: CaseMessage, emit: EmitFn) -> None:
    for delay, kind, payload in _SCRIPT:
        time.sleep(delay)
        emit(AgentEvent(kind=kind, payload=payload))  # type: ignore[arg-type]
    emit(AgentEvent(kind="result", payload={
        "success": True,
        "summary": ("SIMULATION HYPOTHESIS - requires wet-lab validation.\n\n"
                    "This is the mock agent: a canned event sequence used to "
                    "exercise the console with no worker, no database and no API "
                    "key. The numbers shown are fixtures, not simulation output.\n\n"
                    "Start the worker and unset MOCK_AGENT for a real run."),
        "candidate": {"name": "cellulase-WT", "parent_family": "cellulase",
                      "edits": [], "provenance": "wild-type reference"},
        "disclaimer": "Simulation hypothesis only - requires wet-lab validation. "
                      "This system does not provide clinical guidance.",
    }))
