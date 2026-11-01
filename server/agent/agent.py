"""The design loop.

Synchronous by design. A step-by-step loop with explicit guards is far easier
to reason about - and to argue with in review - than an async one, and the
only thing it blocks is its own thread. server/app/main.py runs it in
asyncio.to_thread and pumps its events onto the event loop.

THE DISTINCTIVE CHOICE: the message history is rebuilt from scratch every
turn. The model does not get a growing transcript of its own tool calls. It
gets the task, a plain-text log of what has been attempted, and the CURRENT
BENCH STATE serialized fresh. The reason is the same one that makes a
screenshot-grounded GUI agent work: given a transcript of its own actions a
model assumes they succeeded. Given current state it has to look.

GUARDRAILS ARE PUSHBACK, NOT FAILURE. Almost every guard appends a coaching
line to the action log and continues, rather than erroring out. The one
exception is a safety-gate failure or a clinical-output refusal, which breaks
the loop immediately - because a model handed a soft refusal will rephrase
and try again, and a gate you can rephrase past is not a gate.

Standalone:
    python -m server.agent.agent --case "wood splinter in forearm" --mock-llm
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

from shared.config import settings
from shared.protocol import (
    AgentEvent,
    CaseMessage,
    DesignRun,
    DesignStep,
    EnzymeCandidate,
    FragmentPassport,
    ReactionSpec,
    ToolCall,
)
from shared.safety import (
    ClinicalOutputRefused,
    cap_case_message,
    sanitize_for_prompt,
    simulation_disclaimer,
)

EmitFn = Callable[[AgentEvent], None]

# Pacing after tools whose effects take a moment to settle. Mostly a courtesy
# to the UI so stages do not flash past unread.
_POST_ACTION_DELAY: dict[str, float] = {
    "simulate_hydrogel_assay": 0.3,
    "run_safety_gates": 0.4,
    "rank_candidates": 0.3,
}

# Tools that must have run before a successful finish.
_REQUIRED_BEFORE_SUCCESS = ("run_safety_gates",)


def _print_emit(event: AgentEvent) -> None:
    payload = {k: v for k, v in event.payload.items() if k != "timeseries"}
    text = payload.get("text") or payload.get("msg") or ""
    if event.kind == "thought_delta":
        sys.stdout.write(str(text))
        sys.stdout.flush()
        return
    extra = "" if text else json.dumps(payload, default=str)[:300]
    print(f"\n[{event.kind}] {text or extra}")


def run_design(
    message: CaseMessage,
    emit: EmitFn = _print_emit,
    *,
    mock_llm: bool = False,
    skip_db: bool = False,
    cancel_event: threading.Event | None = None,
    interrupt_event: threading.Event | None = None,
    sim_approved_event: threading.Event | None = None,
    mode: str = "run",
    client_id: str = "default",
) -> DesignRun:
    """Run one design loop to completion. Returns the DesignRun."""
    from server.agent.bench import Bench
    from server.agent.llm import LLMClient, build_turn_message
    from server.agent.tools import (
        TOOL_STAGE,
        dispatch,
        reset_session_limits,
        schemas_for,
    )
    from server.app.bridge import bridge

    case_text = cap_case_message(message.text)
    mode = mode if mode in ("run", "explain") else "run"
    reset_session_limits()

    run = DesignRun(case_summary=case_text[:500], success=False)
    emit(AgentEvent(kind="status", payload={"msg": "Reading the case...", "mode": mode}))

    # ---------------------------------------------------------- preflight

    if not bridge.is_connected(client_id):
        emit(AgentEvent(kind="error", payload={
            "text": "No simulation worker is connected. Start it with:\n"
                    "  python -m client.worker.main --backend ws://localhost:7860 "
                    "--token $WORKER_TOKEN"}))
        return run
    if not (mock_llm or settings.llm_api_key or settings.openrouter_api_key
            or settings.gemini_api_key):
        emit(AgentEvent(kind="error", payload={
            "text": "No LLM API key configured. Set LLM_API_KEY in .env, or run with "
                    "MOCK_LLM=1 for the scripted demo."}))
        return run

    bench = Bench(client_id=client_id, skip_db=skip_db, mode=mode)
    llm = LLMClient(mock=mock_llm, mode=mode)
    tools = schemas_for(mode)

    action_log: list[str] = []
    steps: list[DesignStep] = []
    hint = ""

    # Prior similar runs, spliced in as a trusted hint. Everything retrieved
    # goes through sanitize_for_prompt first - a stored summary is untrusted
    # text that is about to be read by the model as if we had written it.
    if not skip_db:
        try:
            from server.db.client import search_similar_runs

            for m in search_similar_runs(case_text, top_k=3):
                if m.score >= settings.similarity_threshold and m.record.chosen_candidate:
                    hint = sanitize_for_prompt(
                        f"A similar case was run before and selected "
                        f"{m.record.chosen_candidate.name} "
                        f"({m.record.chosen_candidate.parent_family}). Treat this as a "
                        f"starting point to verify, not an answer to reuse.", 400)
                    emit(AgentEvent(kind="status", payload={
                        "msg": f"Found a similar prior run (similarity {m.score:.2f})"}))
                    break
        except Exception as e:  # noqa: BLE001
            print(f"[agent] prior-run lookup skipped: {e}")

    # ---------------------------------------------------------- helpers

    def _cancelled() -> bool:
        return cancel_event is not None and cancel_event.is_set()

    def _interrupted() -> bool:
        return interrupt_event is not None and interrupt_event.is_set()

    def _wait_for_resume() -> bool:
        """Block while paused. Returns False if cancelled while waiting."""
        if not _interrupted():
            return True
        emit(AgentEvent(kind="status", payload={"msg": "paused", "paused": True}))
        while _interrupted():
            if _cancelled():
                return False
            time.sleep(0.25)
        emit(AgentEvent(kind="status", payload={"msg": "resuming", "paused": False}))
        return True

    def _state_json() -> str:
        """The bench state the model judges from. Traces are summarized, not
        dumped - a 60-point time series per candidate would crowd out the
        reasoning and tell the model nothing it cannot get from the summary."""
        st = bench.state
        assays = {}
        for name, a in st["assays"].items():
            assays[name] = {
                "erosion_rate_um_per_day": a.get("erosion_rate_um_per_day"),
                "erosion_rate_ci": a.get("erosion_rate_ci"),
                "uncertainty": a.get("uncertainty"),
                "consumed_fraction": a.get("consumed_fraction"),
                "captured_fraction": a.get("captured_fraction"),
                "free_fraction": a.get("free_fraction"),
                "particle_fraction_p95": a.get("particle_fraction_p95"),
                "mass_balance_residual": a.get("mass_balance_residual"),
                "conditions": a.get("conditions"),
                "n_points": len(a.get("timeseries") or []),
            }
        return json.dumps({
            "passport": st["passport"],
            "reaction_spec": st["reaction_spec"],
            "substrate": st["substrate"],
            "retrieved_families": [
                {k: f.get(k) for k in ("name", "substrate_material", "reaction_class",
                                       "kinetics", "conditions", "score")}
                for f in st["families"]],
            "precedents": st["precedents"],
            "candidates": st["candidates"],
            "developability": st["properties"],
            "assays": assays,
            "gates": {k: {"passed": v.get("passed"), "failed": v.get("failed"),
                          "summary": v.get("summary")}
                      for k, v in st["gates"].items()},
            "ranking": st["ranking"],
            "next_experiments": st["next_experiments"],
            "submitted": st["submitted"],
        }, indent=1, default=str)[:14000]

    def _build_turn_messages() -> list[dict[str, Any]]:
        body = f"## Case\n{case_text}\n\n"
        if hint:
            body += f"[TRUSTED SYSTEM HINT: {hint}]\n\n"
        if action_log:
            body += "## Actions attempted so far\n"
            body += "\n".join(f"{i + 1}. {a}" for i, a in enumerate(action_log[-30:]))
            body += ("\n\nThey may have worked, partially worked, been clamped or been "
                     "rejected. Do NOT assume any of them succeeded - judge from the "
                     "bench state below.\n\n")
        body += f"## Bench state\n```json\n{_state_json()}\n```"
        return [
            {"role": "system",
             "content": [{"type": "text", "text": llm.system_prompt,
                          "cache_control": {"type": "ephemeral"}}]},
            build_turn_message(body),
        ]

    def _emit_stage(tool: str) -> None:
        stage = TOOL_STAGE.get(tool, "")
        if stage:
            emit(AgentEvent(kind="stage", payload={"stage": stage, "tool": tool}))

    # ---------------------------------------------------------- the loop

    final_summary = ""
    halted = False
    last_tools: list[str] = []
    distinct_actions: set[str] = set()

    for turn in range(settings.agent_max_steps):
        if _cancelled():
            emit(AgentEvent(kind="status", payload={"msg": "cancelled"}))
            break
        if not _wait_for_resume():
            emit(AgentEvent(kind="status", payload={"msg": "cancelled"}))
            break

        messages = _build_turn_messages()

        # Streamed reasoning: one empty thought bubble, then deltas into it.
        delta_started = {"v": False}

        # `started` is bound as a default argument on purpose: the closure must
        # own this turn's flag, not whatever the loop variable happens to be
        # by the time it runs.
        def _on_delta(piece: str, started: dict = delta_started) -> None:
            if not started["v"]:
                emit(AgentEvent(kind="thought", payload={"text": "", "stream": True}))
                started["v"] = True
            emit(AgentEvent(kind="thought_delta", payload={"text": piece}))

        try:
            thought, calls = llm.chat(messages, tools, on_thought_delta=_on_delta,
                                      interrupt_event=interrupt_event)
        except Exception as e:  # noqa: BLE001
            emit(AgentEvent(kind="error", payload={"text": f"LLM call failed: {e}"}))
            break

        if thought and not delta_started["v"]:
            emit(AgentEvent(kind="thought", payload={"text": thought}))

        # Paused mid-stream: drop the partial call and re-enter cleanly.
        if _interrupted():
            if not _wait_for_resume():
                break
            action_log.append("(turn interrupted mid-stream; the partial tool call was "
                              "discarded - re-decide from the bench state)")
            continue

        if not calls:
            action_log.append("You produced no tool call. Pick the next pipeline stage "
                              "and call its tool, or call finish with a report.")
            continue

        finished = False
        for call in calls:
            if _cancelled():
                break
            name = str(call.name)

            # --- explain-mode rewrite: run/write tools become annotations
            if mode == "explain" and name in ("simulate_hydrogel_assay", "score_kinetics",
                                              "submit_candidate"):
                stage = TOOL_STAGE.get(name, "simulate")
                call = ToolCall(name="highlight_step", args={
                    "stage": stage,
                    "label": f"would run {name}",
                    "detail": "Explain mode does not execute simulations or write to "
                              "the library. Describe what this step would measure and "
                              "what its result would mean."})
                name = "highlight_step"

            # --- anti-loop: same tool three times running
            if len(last_tools) >= 2 and last_tools[-1] == last_tools[-2] == name:
                action_log.append(f"STOP REPEATING {name} - you have called it three "
                                  f"times in a row with no progress. Read the bench "
                                  f"state and move to a different stage, or finish.")
                last_tools.append(name)
                continue

            # --- refuse two consecutive waits
            if name == "wait" and last_tools and last_tools[-1] == "wait":
                action_log.append("Two waits in a row achieve nothing. Act or finish.")
                continue

            # --- finish guards
            if name == "finish":
                success = bool(call.args.get("success", False))
                if turn == 0:
                    action_log.append("You cannot finish on the first turn - nothing "
                                      "has been characterized, simulated or gated yet.")
                    continue
                if success:
                    missing = [t for t in _REQUIRED_BEFORE_SUCCESS
                               if t not in distinct_actions]
                    if mode == "run" and missing:
                        action_log.append(
                            f"You cannot finish successfully without running "
                            f"{', '.join(missing)}. The gate battery is mandatory.")
                        continue
                    passing = [n for n, g in bench.state["gates"].items() if g.get("passed")]
                    if mode == "run" and not passing:
                        action_log.append(
                            "No candidate has passed its safety gates, so there is no "
                            "successful outcome to report. Either gate a candidate, or "
                            "finish with success=false and explain the no-go.")
                        continue
                elif len(distinct_actions) < 3:
                    action_log.append(
                        "Before reporting failure, actually try: characterize the "
                        "fragment, define the reaction and retrieve candidates. You "
                        "have attempted too little to conclude anything.")
                    continue

            emit(AgentEvent(kind="tool_call", payload={
                "name": name, "stage": TOOL_STAGE.get(name, "")}))
            _emit_stage(name)

            # --- dispatch
            try:
                result = dispatch(call, bench, mode=mode)
            except ClinicalOutputRefused as e:
                # HARD STOP. Not negotiable and not retryable.
                emit(AgentEvent(kind="error", payload={"text": str(e)}))
                emit(AgentEvent(kind="result", payload={
                    "success": False, "summary": str(e), "halted": "clinical_output"}))
                halted = True
                finished = True
                final_summary = str(e)
                break

            last_tools.append(name)
            distinct_actions.add(name)

            if "error" in result:
                emit(AgentEvent(kind="observation", payload={
                    "name": name, "error": result["error"]}))
                action_log.append(f"{name} was REJECTED: {result['error']}")
                continue

            payload = result.get("result")
            steps.append(DesignStep(action=call, note=None))

            emit(AgentEvent(kind="observation", payload={
                "name": name, "result": payload}))
            action_log.append(f"{name} -> {_summarize(name, payload)}")

            # --- capture state into the run record
            if name == "characterize_fragment" and isinstance(payload, dict):
                try:
                    run.passport = FragmentPassport(**payload["passport"])
                except Exception:  # noqa: BLE001
                    pass
                if payload.get("no_go"):
                    action_log.append(
                        f"NO-GO: {payload.get('no_go_reason')}. Report this as the "
                        f"finding; do not substitute a weaker material.")
            if name == "define_reaction" and isinstance(payload, dict) and payload.get("ok"):
                try:
                    run.reaction_spec = ReactionSpec(**payload["reaction_spec"])
                except Exception:  # noqa: BLE001
                    pass

            # --- THE HARD GATE
            if name == "run_safety_gates" and isinstance(payload, dict):
                if payload.get("blocking"):
                    detail = "; ".join(
                        f"{g['name']}={g.get('value')} (limit {g.get('threshold')})"
                        for g in payload.get("gates", []) if not g.get("passed"))
                    text = (f"SAFETY GATE FAILURE - run halted. "
                            f"{payload.get('summary')}. {detail}. "
                            f"This is not a parameter to tune around: a candidate that "
                            f"fails a gate is a finding, not a draft.")
                    emit(AgentEvent(kind="error", payload={"text": text}))
                    emit(AgentEvent(kind="result", payload={
                        "success": False, "summary": text,
                        "gates": payload.get("gates", []),
                        "halted": "safety_gate"}))
                    halted = True
                    finished = True
                    final_summary = text
                    break

            if name == "finish" and isinstance(payload, dict):
                final_summary = str(payload.get("summary", ""))
                success = bool(payload.get("success"))
                # Supervisor check. Its feedback replaces the summary.
                emit(AgentEvent(kind="status", payload={"msg": "Verifying the report..."}))
                try:
                    from server.agent.supervisor import verify_finish

                    verdict = verify_finish(case_text, final_summary, bench.state)
                    if not verdict.get("approved"):
                        final_summary = verdict.get("feedback") or final_summary
                except Exception as e:  # noqa: BLE001
                    print(f"[agent] supervisor skipped: {e}")
                run.success = success
                finished = True
                break

            delay = _POST_ACTION_DELAY.get(name, 0.0)
            if delay:
                time.sleep(delay)

        if finished or _cancelled():
            break
    else:
        emit(AgentEvent(kind="error", payload={
            "text": f"Reached the step limit ({settings.agent_max_steps}) without "
                    f"finishing. Partial results are in the bench state."}))

    # ---------------------------------------------------------- wrap up

    run.steps = steps
    best = (bench.state["ranking"] or [{}])[0].get("candidate")
    if best:
        cand = next((c for c in bench.state["candidates"] if c.get("name") == best), None)
        if cand:
            try:
                run.chosen_candidate = EnzymeCandidate(
                    name=cand["name"], parent_family=cand.get("parent_family", ""),
                    edits=cand.get("edits", []),
                    scores=bench.state["properties"].get(best, {}),
                    provenance=cand.get("provenance", "in-silico proposal"))
            except Exception:  # noqa: BLE001
                pass

    if not halted and run.success:
        emit(AgentEvent(kind="result", payload={
            "success": True,
            "summary": final_summary or "Run complete.",
            "candidate": run.chosen_candidate.model_dump() if run.chosen_candidate else None,
            "ranking": bench.state["ranking"],
            "gates": next((g.get("gates", []) for g in bench.state["gates"].values()
                           if g.get("passed")), []),
            "assay": next((a for n, a in bench.state["assays"].items() if n == best), None),
            "next_experiments": bench.state["next_experiments"],
            "disclaimer": simulation_disclaimer()}))
    elif not halted:
        emit(AgentEvent(kind="result", payload={
            "success": False,
            "summary": final_summary or "The run did not reach a supported conclusion.",
            "ranking": bench.state["ranking"],
            "disclaimer": simulation_disclaimer()}))

    # Persist the run as a log. The library is only ever written through the
    # approval queue, which bench.submit_candidate goes through.
    if not skip_db:
        try:
            from server.db.client import record_design_run

            run = record_design_run(run)
        except Exception as e:  # noqa: BLE001
            print(f"[agent] run not persisted: {e}")
    return run


def _summarize(name: str, payload: Any) -> str:
    """One readable line per tool result for the action log. The log is
    prose, not JSON, because its job is to tell the model what happened
    without re-feeding it data it can read from the bench state."""
    if not isinstance(payload, dict):
        return str(payload)[:200]
    if name == "characterize_fragment":
        p = payload.get("passport", {})
        return (f"material={p.get('material_family')} confidence={p.get('confidence')} "
                f"source={p.get('source')} no_go={payload.get('no_go')}")
    if name == "define_reaction":
        if not payload.get("ok"):
            return f"REFUSED: {payload.get('reason')}"
        s = payload.get("reaction_spec", {})
        return (f"mechanism={s.get('mechanism')} products={s.get('products')} "
                f"forbidden={s.get('forbidden_products')} "
                f"accessibility={payload.get('substrate', {}).get('accessibility')}")
    if name == "retrieve_enzymes":
        fams = payload.get("families", [])
        return f"{len(fams)} families: " + ", ".join(f.get("name", "?") for f in fams[:5])
    if name == "retrieve_precedents":
        return f"{len(payload.get('precedents', []))} precedents"
    if name == "propose_variants":
        return f"{payload.get('n')} candidates: " + ", ".join(
            c.get("name", "?") for c in payload.get("candidates", [])[:6])
    if name == "predict_properties":
        return f"{payload.get('name')} developability=" \
               f"{payload.get('scores', {}).get('developability')}"
    if name in ("score_kinetics",):
        return (f"{payload.get('name')} {payload.get('erosion_rate_um_per_day')} um/day "
                f"consumed={payload.get('consumed_fraction')}")
    if name == "simulate_hydrogel_assay":
        return (f"{payload.get('candidate')} {payload.get('erosion_rate_um_per_day')} "
                f"um/day band={payload.get('erosion_rate_ci')} "
                f"uncertainty={payload.get('uncertainty')} "
                f"captured={payload.get('captured_fraction')} "
                f"residual={payload.get('mass_balance_residual')}")
    if name == "check_mass_balance":
        return f"passed={payload.get('passed')} residual={payload.get('residual')}"
    if name == "run_safety_gates":
        return payload.get("summary", "")
    if name == "rank_candidates":
        r = payload.get("ranking", [])
        return "ranking: " + ", ".join(
            f"{x.get('candidate')}({x.get('score')},{'pass' if x.get('gates_passed') else 'FAIL'})"
            for x in r[:5])
    if name == "plan_next_experiment":
        return "next: " + ", ".join(
            f"{e.get('candidate')}({e.get('information_value')})"
            for e in payload.get("experiments", []))
    if name == "submit_candidate":
        return payload.get("error") or f"queued {payload.get('candidate')} for review"
    if name == "get_material_notes":
        return f"note for {payload.get('material')} retrieved"
    if name == "read_passport":
        return json.dumps(payload, default=str)[:200]
    if name == "highlight_step":
        return f"annotated stage {payload.get('stage')}"
    return json.dumps(payload, default=str)[:200]


def main() -> int:
    ap = argparse.ArgumentParser(description="ShrapMind design loop (standalone)")
    ap.add_argument("--case", required=True, help="the fragment case description")
    ap.add_argument("--mode", default="run", choices=["run", "explain"])
    ap.add_argument("--mock-llm", action="store_true", help="run the scripted demo")
    ap.add_argument("--skip-db", action="store_true", help="no Postgres")
    ap.add_argument("--client-id", default="default")
    args = ap.parse_args()

    run = run_design(
        CaseMessage(text=args.case, mode=args.mode),  # type: ignore[arg-type]
        mock_llm=args.mock_llm, skip_db=args.skip_db, mode=args.mode,
        client_id=args.client_id)
    print(f"\n\n=== {'SUCCESS' if run.success else 'NO SUPPORTED CONCLUSION'} ===")
    if run.chosen_candidate:
        print(f"candidate: {run.chosen_candidate.name} "
              f"({run.chosen_candidate.provenance})")
    print(f"steps: {len(run.steps)}")
    print(simulation_disclaimer())
    return 0 if run.success else 1


if __name__ == "__main__":
    sys.exit(main())
