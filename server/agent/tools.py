"""Tool registration, validation and dispatch.

Three hand-maintained structures. KEEP THEM IN SYNC:

  1. TOOL_SCHEMAS   - the OpenAI function schemas, passed verbatim as tools=
  2. _ALLOWED_TOOLS - the enforcement allow-list (deny by default)
  3. the methods on server/agent/bench.Bench

Dispatch is duck-typed: `fn = getattr(bench, name)`. There is no registry
decorator, deliberately - a decorator would make the allow-list implicit,
and an implicit allow-list is one you cannot read in a code review. Adding a
tool is four edits (protocol Literal, schema, allow-list, bench method) and
that friction is the feature.

Everything a tool call carries is checked before it is forwarded:
  - name must be in the allow-list
  - clinical-output gate on every string argument
  - numeric bounds on every known parameter
  - per-session caps on simulation calls and candidate count
  - one JSON line per call in the audit log, control characters scrubbed
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from shared.config import settings
from shared.protocol import ToolCall
from shared.safety import (
    ClinicalOutputRefused,
    ParameterOutOfRange,
    check_clinical_output,
    scrub_for_log,
    validate_number,
)

# --------------------------------------------------------------------------
# 1. Schemas
# --------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_passport",
            "description": "Read the current bench state: the fragment passport, the "
                           "reaction spec, how many candidates and assays exist, and "
                           "which candidates have passed their safety gates. Cheap; "
                           "call it whenever you are unsure what has already been done.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "characterize_fragment",
            "description": "Build a fragment passport from the case description and any "
                           "instrument data. Returns the material family with a "
                           "confidence score. A confidence of 0 means the material was "
                           "NOT identified - that is a valid and important result, and "
                           "you must not design against a guess.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string",
                                    "description": "The case text describing the fragment."},
                    "spectra": {"type": "object",
                                "description": "Optional instrument data: "
                                               "{'peaks': [cm-1...], 'elements': {'Fe': 72}}."},
                    "volume_mm3": {"type": "number", "description": "Fragment volume in mm3."},
                    "anatomy_class": {"type": "string",
                                      "enum": ["soft_tissue", "peri_articular", "near_nerve",
                                               "intra_articular", "vascular", "cns", "ocular"]},
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "define_reaction",
            "description": "Turn a material family into an explicit chemistry target: bond "
                           "class, mechanism, expected products, and the products that "
                           "must never appear. Call this before retrieving enzymes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "material_family": {"type": "string"},
                    "surface_state": {"type": "string",
                                      "enum": ["unknown", "pristine", "oxidised", "coated",
                                               "crystalline", "semi-crystalline"]},
                },
                "required": ["material_family"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_material_notes",
            "description": "Retrieve the guidance note for one material family: what the "
                           "real rate limit is, and what would make a confident answer "
                           "wrong. Call this once you know the material.",
            "parameters": {
                "type": "object",
                "properties": {"material": {"type": "string"}},
                "required": ["material"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_enzymes",
            "description": "Semantic search over the enzyme knowledge base for families "
                           "matching a reaction. Pass `material` to restrict to families "
                           "measured on that substrate - without it, similarity will "
                           "happily return the right mechanism on the wrong material.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string",
                              "description": "Reaction description, e.g. "
                                             "'beta-1,4-glycosidic hydrolysis of solid cellulose'."},
                    "material": {"type": "string"},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 25},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_precedents",
            "description": "Retrieve literature precedents. Each one carries BOTH what it "
                           "proves and what it does NOT prove; you are required to carry "
                           "the second half into your final report.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 25},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_variants",
            "description": "Enumerate candidate variants of a parent enzyme family over a "
                           "documented edit catalogue. These are sequence-level proposals "
                           "only - no folding, expression or binding is predicted.",
            "parameters": {
                "type": "object",
                "properties": {
                    "parent_family": {"type": "string"},
                    "base_params": {"type": "object",
                                    "description": "Kinetic record and substrate geometry."},
                    "n_variants": {"type": "integer", "minimum": 1, "maximum": 25},
                    "goal": {"type": "string", "enum": ["balanced", "activity", "stability", "safety"]},
                },
                "required": ["parent_family"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "predict_properties",
            "description": "Heuristic developability scores for one candidate (activity, "
                           "stability, solubility, expression, immunogenicity). Returns the "
                           "per-edit contributions so the score can be audited. This is an "
                           "additive heuristic, not a trained model.",
            "parameters": {
                "type": "object",
                "properties": {"candidate": {"type": "object"}},
                "required": ["candidate"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "score_kinetics",
            "description": "Fast point estimate of surface erosion for one candidate. Use "
                           "to shortlist before spending a full assay.",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate": {"type": "object"},
                    "base_params": {"type": "object"},
                    "conditions": {"type": "object",
                                   "description": "temperature_c, ph, enzyme_uM, "
                                                  "serum_fraction, hours."},
                    "product": {"type": "string"},
                },
                "required": ["candidate"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_hydrogel_assay",
            "description": "The virtual experiment. Simulates the candidate acting on the "
                           "fragment inside the hydrogel and returns a time series, an "
                           "erosion-rate band (5-95 percentile), capture and particle "
                           "fractions, and the mass-balance residual. Expensive - run it "
                           "on shortlisted candidates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate": {"type": "object"},
                    "base_params": {"type": "object"},
                    "conditions": {"type": "object"},
                    "product": {"type": "string"},
                    "n_samples": {"type": "integer", "minimum": 1, "maximum": 512},
                    "seed": {"type": "integer"},
                },
                "required": ["candidate"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_mass_balance",
            "description": "Verify an assay conserved mass. A run whose mass balance does "
                           "not close is numerically invalid and no conclusion may be drawn "
                           "from it.",
            "parameters": {
                "type": "object",
                "properties": {"assay": {"type": "object"}, "tolerance": {"type": "number"}},
                "required": ["assay"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_safety_gates",
            "description": "Run the full gate battery on an assay: mass balance, "
                           "fragmentation, free product, capture efficiency, forbidden "
                           "products, predictive confidence, meaningful erosion, tissue "
                           "off-target, anatomical tier, material identification. REQUIRED "
                           "before submitting a candidate or finishing successfully. A "
                           "failed gate stops the run - it is not feedback to work around.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assay": {"type": "object"},
                    "reaction_spec": {"type": "object"},
                    "passport": {"type": "object"},
                    "candidate": {"type": "object"},
                },
                "required": ["assay"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rank_candidates",
            "description": "Multi-objective ranking over everything simulated so far. "
                           "Candidates that failed a gate are listed but never ranked above "
                           "one that passed.",
            "parameters": {
                "type": "object",
                "properties": {"weights": {"type": "object",
                                           "description": "erosion, developability, confidence"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_next_experiment",
            "description": "Rank wet-lab experiments by how much uncertainty each would "
                           "remove. Use this to close the report with what to measure next.",
            "parameters": {
                "type": "object",
                "properties": {"budget": {"type": "integer", "minimum": 1, "maximum": 10}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "highlight_step",
            "description": "Annotate one pipeline stage for the user. Explain mode's main "
                           "tool: it teaches what happens at a stage without running it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stage": {"type": "string",
                              "enum": ["inspect", "characterize", "reaction", "retrieve",
                                       "generate", "predict", "simulate", "gate", "rank",
                                       "report"]},
                    "label": {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["stage"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_candidate",
            "description": "Queue a gate-passing candidate for human scientific review. It "
                           "does NOT enter the validated library until a reviewer approves "
                           "it. Refused if the candidate has no gates or failed any.",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_name": {"type": "string"},
                    "summary": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["candidate_name", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Pause briefly. Rarely useful; two in a row are refused.",
            "parameters": {"type": "object",
                           "properties": {"seconds": {"type": "number", "maximum": 5}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "End the run with a report. State the chosen candidate, its "
                           "erosion band, which gates passed, what the precedents do NOT "
                           "prove, and what to measure next. Never describe a candidate as "
                           "validated, safe or ready for use.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "success": {"type": "boolean"},
                },
                "required": ["summary", "success"],
            },
        },
    },
]

# --------------------------------------------------------------------------
# 2. Allow-list. Deny by default.
# --------------------------------------------------------------------------

_ALLOWED_TOOLS: set[str] = {
    # inspect
    "read_passport", "characterize_fragment", "define_reaction", "get_material_notes",
    # design
    "retrieve_enzymes", "retrieve_precedents", "propose_variants", "predict_properties",
    # validate
    "score_kinetics", "simulate_hydrogel_assay", "check_mass_balance", "run_safety_gates",
    # decide
    "rank_candidates", "plan_next_experiment", "highlight_step", "submit_candidate",
    # control
    "wait", "finish",
}

# Tools that consume real worker compute or write to the database. Capped
# per session, and disabled entirely in explain mode.
_COSTLY_TOOLS = frozenset({
    "simulate_hydrogel_assay", "score_kinetics", "propose_variants", "submit_candidate",
})

# In explain mode the agent may look and describe, but not run or write.
_EXPLAIN_BLOCKED = frozenset({
    "simulate_hydrogel_assay", "score_kinetics", "submit_candidate",
})

# Which pipeline stage each tool belongs to - drives the UI strip. An empty
# string means "does not advance the pipeline", which is not the same as
# missing: _selfcheck() requires every allowed tool to appear here, so a new
# tool cannot silently fail to light up the UI.
TOOL_STAGE: dict[str, str] = {
    "wait": "",
    "read_passport": "inspect",
    "characterize_fragment": "characterize",
    "define_reaction": "reaction",
    "get_material_notes": "reaction",
    "retrieve_enzymes": "retrieve",
    "retrieve_precedents": "retrieve",
    "propose_variants": "generate",
    "predict_properties": "predict",
    "score_kinetics": "predict",
    "simulate_hydrogel_assay": "simulate",
    "check_mass_balance": "simulate",
    "run_safety_gates": "gate",
    "rank_candidates": "rank",
    "plan_next_experiment": "rank",
    "submit_candidate": "report",
    "highlight_step": "inspect",
    "finish": "report",
}


# --------------------------------------------------------------------------
# Per-session caps
# --------------------------------------------------------------------------

_session_lock = threading.Lock()
_session_state: dict[str, int] = {"sim_calls": 0, "candidates": 0}


def reset_session_limits() -> None:
    with _session_lock:
        _session_state["sim_calls"] = 0
        _session_state["candidates"] = 0


def session_usage() -> dict[str, int]:
    with _session_lock:
        return dict(_session_state)


def _bump(key: str, n: int = 1) -> int:
    with _session_lock:
        _session_state[key] = _session_state.get(key, 0) + n
        return _session_state[key]


# --------------------------------------------------------------------------
# Audit log
# --------------------------------------------------------------------------


def _default_audit_path() -> Path:
    explicit = os.getenv("SHRAPMIND_AUDIT_LOG")
    if explicit:
        return Path(explicit)
    return Path.home() / ".shrapmind" / "audit.log"


_AUDIT_ROTATE_BYTES = int(os.getenv("SHRAPMIND_AUDIT_ROTATE_BYTES", str(8 * 1024 * 1024)))


def _audit(event: str, name: str, args: dict[str, Any], result: Any = None) -> None:
    """One JSON line per call. Control characters are scrubbed out of every
    field so a tool argument cannot forge an extra log line."""
    try:
        path = _default_audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > _AUDIT_ROTATE_BYTES:
            path.replace(path.with_suffix(path.suffix + ".1"))
        record = {
            "ts": round(time.time(), 3),
            "event": event,
            "tool": scrub_for_log(name, 80),
            "args": {str(k)[:40]: scrub_for_log(v, 200) for k, v in (args or {}).items()},
        }
        if result is not None:
            record["result"] = scrub_for_log(result, 300)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=True) + "\n")
    except Exception as e:  # noqa: BLE001 - logging must never break a run
        print(f"Warning: could not write audit log: {e}")


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

# Numeric arguments that get bounds-checked, mapped onto the canonical name
# shared.safety.BOUNDS knows.
_NUMERIC_ARGS: dict[str, str] = {
    "volume_mm3": "fragment_volume_mm3",
    "n_samples": "n_samples",
    "n_variants": "n_variants",
    "top_k": "top_k",
    "seconds": "hours",  # bounded separately below
}

_CONDITION_KEYS = {"temperature_c", "ph", "enzyme_uM", "serum_fraction", "hours",
                   "timestep_h", "mesh_nm", "gel_volume_ul"}


def _validate_args(call: ToolCall, mode: str = "run") -> dict[str, Any] | None:
    """Check one call. Returns a rejection dict, or None to proceed.

    Mutates call.args in place to clamp where clamping is clearly right
    (budget, tolerance) and rejects where a wrong value would silently
    produce a plausible-looking wrong answer (every physical parameter).
    """
    name = call.name
    args = call.args

    # Clinical-output gate on every string the model produced. This raises
    # rather than returning, because the agent loop treats it as a hard stop.
    for k, v in args.items():
        if isinstance(v, str) and v:
            check_clinical_output(v, where=f"{name}.{k}")

    if name in _EXPLAIN_BLOCKED and mode == "explain":
        return {"error": f"{name} is disabled in explain mode. Explain mode describes "
                         f"the pipeline; it does not run simulations or write to the "
                         f"library. Use highlight_step to annotate this stage instead."}

    # Per-session caps.
    if name in ("simulate_hydrogel_assay", "score_kinetics"):
        used = _bump("sim_calls")
        cap = settings.max_sim_calls_per_session
        if used > cap:
            return {"error": f"simulation cap reached ({cap} calls this session). "
                             f"Rank what you already have and finish, or report that "
                             f"the search did not converge."}
    if name == "propose_variants":
        try:
            n = int(args.get("n_variants", 5))
        except (TypeError, ValueError):
            n = 5
        used = _bump("candidates", max(n, 1))
        cap = settings.max_candidates_per_session
        if used > cap:
            return {"error": f"candidate cap reached ({cap} this session). Narrow the "
                             f"search rather than widening it."}

    # Numeric bounds. Integer-valued arguments are cast back to int after
    # validation: validate_number returns a float, and a float reaching a
    # slice index or a range() is a TypeError the model cannot do anything
    # useful about.
    _INT_ARGS = {"top_k", "n_samples", "n_variants"}
    try:
        for arg_name, canonical in _NUMERIC_ARGS.items():
            if arg_name in args and args[arg_name] is not None:
                if arg_name == "seconds":
                    args[arg_name] = max(0.0, min(float(args[arg_name]), 5.0))
                else:
                    checked = validate_number(canonical, args[arg_name])
                    args[arg_name] = int(checked) if arg_name in _INT_ARGS else checked
        conds = args.get("conditions")
        if isinstance(conds, dict):
            for k in list(conds):
                if k in _CONDITION_KEYS and conds[k] is not None:
                    conds[k] = validate_number(k, conds[k])
        base = args.get("base_params")
        if isinstance(base, dict):
            for k in list(base):
                if k in _CONDITION_KEYS and base[k] is not None:
                    base[k] = validate_number(k, base[k])
                if k == "volume_mm3" and base[k] is not None:
                    base[k] = validate_number("fragment_volume_mm3", base[k])
    except ParameterOutOfRange as e:
        return {"error": f"parameter rejected: {e}. Physical parameters are bounded; "
                         f"pick a value inside the legal range rather than one that "
                         f"would produce a number with no meaning."}

    # Clamp the harmless ones.
    if "budget" in args:
        try:
            args["budget"] = max(1, min(int(args["budget"]), 10))
        except (TypeError, ValueError):
            args["budget"] = 3
    if "tolerance" in args:
        try:
            args["tolerance"] = max(1e-12, min(float(args["tolerance"]), 1e-2))
        except (TypeError, ValueError):
            args["tolerance"] = 1e-6

    # finish must say something.
    if name == "finish":
        summary = str(args.get("summary", "")).strip()
        if len(summary) < 40:
            return {"error": "finish needs a real report: the chosen candidate, its "
                             "erosion band, which gates passed, what the precedents do "
                             "not prove, and what to measure next."}
    return None


# --------------------------------------------------------------------------
# 3. Dispatch
# --------------------------------------------------------------------------


def dispatch(call: ToolCall, bench: Any, mode: str = "run") -> dict[str, Any]:
    """Validate and forward one tool call.

    Returns {"ok": True, "result": ...} on success, or {"error": "..."} on
    rejection. Note that rejections deliberately omit "ok" - the agent loop
    keys off that to tell a refusal from a result.

    ClinicalOutputRefused is allowed to propagate: the loop catches it and
    halts. Everything else becomes an error string the model can react to.
    """
    name = str(call.name)
    if name not in _ALLOWED_TOOLS:
        _audit("rejected", name, call.args, "not in allow-list")
        return {"error": f"tool {name!r} is not permitted"}

    rejection = _validate_args(call, mode)
    if rejection is not None:
        _audit("rejected", name, call.args, rejection.get("error"))
        return rejection

    fn = getattr(bench, name, None)
    if fn is None or not callable(fn):
        _audit("rejected", name, call.args, "no bench method")
        return {"error": f"tool {name!r} has no implementation"}

    _audit("call", name, call.args)
    try:
        result = fn(**call.args)
    except ClinicalOutputRefused:
        raise
    except TypeError as e:
        _audit("error", name, call.args, str(e))
        return {"error": f"bad args for {name}: {e}"}
    except Exception as e:  # noqa: BLE001
        _audit("error", name, call.args, f"{type(e).__name__}: {e}")
        return {"error": f"{type(e).__name__}: {e}"}
    _audit("result", name, call.args, result)
    return {"ok": True, "result": result}


def tool_names() -> list[str]:
    return sorted(_ALLOWED_TOOLS)


def schemas_for(mode: str = "run") -> list[dict[str, Any]]:
    """The schema list the model actually sees. In explain mode the tools
    that would run or write are withheld entirely, rather than offered and
    then refused - offering a tool you will reject just wastes a turn."""
    if mode != "explain":
        return TOOL_SCHEMAS
    return [s for s in TOOL_SCHEMAS if s["function"]["name"] not in _EXPLAIN_BLOCKED]


def _selfcheck() -> list[str]:
    """Verify the three structures agree. Called by the test suite."""
    from shared.protocol import ToolName

    problems: list[str] = []
    literal = set(ToolName.__args__)  # type: ignore[attr-defined]
    schema_names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    if schema_names != _ALLOWED_TOOLS:
        problems.append(f"schemas vs allow-list differ: "
                        f"{schema_names ^ _ALLOWED_TOOLS}")
    if _ALLOWED_TOOLS != literal:
        problems.append(f"allow-list vs ToolName differ: {_ALLOWED_TOOLS ^ literal}")
    if set(TOOL_STAGE) != _ALLOWED_TOOLS:
        problems.append(f"TOOL_STAGE vs allow-list differ: {set(TOOL_STAGE) ^ _ALLOWED_TOOLS}")
    return problems
