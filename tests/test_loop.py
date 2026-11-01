"""The design loop: the happy path, and the two hard stops."""
from shared.protocol import AgentEvent, CaseMessage, ToolCall


def _collect():
    events: list[AgentEvent] = []
    return events, events.append


def _run(script=None, **kw):
    from server.agent.agent import run_design
    from server.agent.llm import LLMClient
    from server.agent.mock_llm import MockLLM

    events, emit = _collect()
    if script is not None:
        orig = LLMClient.__init__

        def patched(self, mock=False, mode="run"):
            orig(self, mock=True, mode=mode)
            self._mock_impl = MockLLM(script)

        LLMClient.__init__ = patched  # type: ignore[method-assign]
        try:
            run = run_design(CaseMessage(text=kw.pop("case", "wood splinter in forearm")),
                             emit, mock_llm=True, skip_db=True, **kw)
        finally:
            LLMClient.__init__ = orig  # type: ignore[method-assign]
    else:
        run = run_design(CaseMessage(text=kw.pop("case", "wood splinter in forearm")),
                         emit, mock_llm=True, skip_db=True, **kw)
    return run, events


def _kinds(events):
    out: dict[str, int] = {}
    for e in events:
        out[e.kind] = out.get(e.kind, 0) + 1
    return out


def _result(events):
    return next((e for e in reversed(events) if e.kind == "result"), None)


# ---------------------------------------------------------------- happy path


def test_scripted_run_reports_an_evidence_no_go(fake_worker):
    """The demo runs a PET case on the real warehouse, where every available
    turnover number was measured on a chromogenic stand-in. The correct
    outcome is therefore a reasoned refusal, not a recommendation - and the
    report has to distinguish "no evidence" from "will not work"."""
    run, events = _run()
    assert not run.success
    res = _result(events)
    assert res is not None
    assert res.payload["success"] is False
    assert res.payload["halted"] == "safety_gate"
    summary = res.payload["summary"]
    assert "requires wet-lab validation" in summary
    # The distinction that matters scientifically.
    assert "does NOT establish" in summary
    assert "nobody has measured" in summary
    # It must name the substrate the constant actually came from.
    assert "4-nitrophenyl butanoate" in summary


def test_a_failed_gate_still_produces_a_written_report(fake_worker):
    """A gate failure ends the recommendation, not the run. Breaking
    immediately would throw away the write-up and keep only the error."""
    run, events = _run()
    called = [e.payload["name"] for e in events if e.kind == "tool_call"]
    assert "finish" in called, "the agent must still get to write its no-go report"
    # But it may not route around the gate.
    gated_after = called[called.index("run_safety_gates") + 1:]
    assert "simulate_hydrogel_assay" not in gated_after
    assert "submit_candidate" not in gated_after


def test_the_experiment_plan_survives_a_gate_failure(fake_worker):
    """The most valuable output of a refused run is what to measure next."""
    _, events = _run()
    res = _result(events)
    assert res is not None
    assert res.payload.get("next_experiments")


def test_every_pipeline_stage_is_announced(fake_worker):
    _, events = _run()
    stages = {e.payload["stage"] for e in events if e.kind == "stage"}
    for expected in ("characterize", "reaction", "retrieve", "generate", "predict",
                     "simulate", "gate", "rank", "report"):
        assert expected in stages, expected


def test_reasoning_is_streamed_not_dumped(fake_worker):
    _, events = _run()
    k = _kinds(events)
    assert k.get("thought", 0) > 0
    assert k.get("tool_call", 0) > 0


def test_run_record_captures_passport_and_candidate(fake_worker):
    run, _ = _run()
    assert run.passport is not None
    assert run.passport.material_family == "pet"
    assert run.reaction_spec is not None
    assert run.chosen_candidate is not None
    assert run.chosen_candidate.provenance in ("in-silico proposal", "wild-type reference")


# ---------------------------------------------------------------- hard stops


def test_a_failing_gate_halts_the_run(fake_worker):
    """The loop must stop on a gate failure, not hand the model a soft error
    it can rephrase past."""
    leaky = {"k_cat": 3.0, "k_m_uM": 45.0, "half_life_h": 96.0, "volume_mm3": 8.0,
             "accessibility": 0.3, "mesh_nm": 20.0, "molar_mass_g_mol": 162.14,
             "density_g_cm3": 1.5, "fragmentation_fraction": 0.2,
             "capture_rate_per_h": 0.01, "capture_capacity_umol": 1.0}
    cand = {"name": "bad", "parent_family": "cellulase", "edits": []}
    script = [
        ("Characterizing.", [ToolCall(name="characterize_fragment",
                                     args={"description": "wood splinter", "volume_mm3": 8.0})]),
        ("Reaction.", [ToolCall(name="define_reaction",
                                args={"material_family": "cellulose"})]),
        ("Simulating.", [ToolCall(name="simulate_hydrogel_assay",
                                  args={"candidate": cand, "base_params": leaky,
                                        "conditions": {"hours": 336.0},
                                        "product": "cellobiose", "n_samples": 24})]),
        ("Gating.", [ToolCall(name="run_safety_gates", args={})]),
        # The model tries to finish successfully anyway. It must not get there.
        ("Reporting success.", [ToolCall(name="finish", args={
            "success": True,
            "summary": "A good candidate was found and all is well, this is a long "
                       "enough summary to pass the length check easily."})]),
    ]
    run, events = _run(script)
    assert not run.success
    res = _result(events)
    assert res is not None
    assert res.payload["halted"] == "safety_gate"
    # The gate failure is surfaced as an error event with its deciding numbers.
    errors = [e.payload.get("text", "") for e in events if e.kind == "error"]
    assert any("SAFETY GATE FAILURE" in t for t in errors)
    # And the attempt to declare success anyway was refused, not merely
    # unreachable - the model asked, and was told no.
    assert res.payload["success"] is False


def test_a_clinical_request_halts_the_run(fake_worker):
    """Asking for dosing must stop the run, not be answered or negotiated."""
    script = [
        ("Characterizing.", [ToolCall(name="characterize_fragment",
                                      args={"description": "wood splinter"})]),
        ("Answering the dosing question.", [ToolCall(name="highlight_step", args={
            "stage": "report", "label": "dosing",
            "detail": "The recommended dose for this patient is 2 ml injected into "
                      "the forearm every 6 hours per dose."})]),
    ]
    run, events = _run(script)
    assert not run.success
    res = _result(events)
    assert res is not None
    assert res.payload["halted"] == "clinical_output"
    assert "clinical-output gate" in res.payload["summary"]


# ---------------------------------------------------------------- guardrails


def test_finish_is_refused_on_the_first_turn(fake_worker):
    script = [
        ("Finishing immediately.", [ToolCall(name="finish", args={
            "success": True,
            "summary": "Everything is fine and this summary is comfortably long "
                       "enough to clear the minimum length requirement."})]),
        ("Fine, characterizing.", [ToolCall(name="characterize_fragment",
                                            args={"description": "wood splinter"})]),
    ]
    run, events = _run(script)
    assert not run.success
    # It was pushed back, then did real work on the next turn.
    assert any(e.payload["name"] == "characterize_fragment"
               for e in events if e.kind == "tool_call")


def test_success_requires_the_gate_battery(fake_worker):
    """finish(success=True) without run_safety_gates must be pushed back."""
    script = [
        ("Characterizing.", [ToolCall(name="characterize_fragment",
                                      args={"description": "wood splinter"})]),
        ("Claiming success without gating.", [ToolCall(name="finish", args={
            "success": True,
            "summary": "Found an excellent candidate, skipping the tedious gate "
                       "battery because I am confident in the result."})]),
        ("Characterizing again.", [ToolCall(name="read_passport", args={})]),
    ]
    run, events = _run(script)
    assert not run.success


def test_explain_mode_withholds_the_simulation_tools(fake_worker):
    from server.agent.tools import schemas_for

    names = {s["function"]["name"] for s in schemas_for("explain")}
    assert "simulate_hydrogel_assay" not in names
    assert "submit_candidate" not in names
    assert "retrieve_enzymes" in names
    assert "highlight_step" in names


def test_explain_mode_rewrites_a_simulation_call_into_an_annotation(fake_worker):
    script = [
        ("Characterizing.", [ToolCall(name="characterize_fragment",
                                      args={"description": "wood splinter"})]),
        ("Trying to simulate anyway.", [ToolCall(name="simulate_hydrogel_assay", args={
            "candidate": {"name": "x", "parent_family": "cellulase", "edits": []}})]),
    ]
    run, events = _run(script, mode="explain")
    called = [e.payload["name"] for e in events if e.kind == "tool_call"]
    assert "simulate_hydrogel_assay" not in called
    assert "highlight_step" in called


def test_no_worker_connected_is_reported_clearly(monkeypatch):
    import server.agent.bench as bench_mod
    import server.app.bridge as bridge_mod

    class Down:
        def is_connected(self, client_id="default"):
            return False

    monkeypatch.setattr(bridge_mod, "bridge", Down())
    monkeypatch.setattr(bench_mod, "bridge", Down())
    run, events = _run()
    assert not run.success
    err = next(e for e in events if e.kind == "error")
    assert "No simulation worker" in err.payload["text"]
