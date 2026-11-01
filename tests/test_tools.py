"""The tool registry's three structures must agree, and validation must bite."""
import pytest

from server.agent import tools as T
from shared.protocol import ToolCall
from shared.safety import ClinicalOutputRefused


def test_schemas_allowlist_and_tool_literal_agree():
    """This is the test that catches the commonest mistake in this design:
    adding a tool in three of the four places it has to exist."""
    assert T._selfcheck() == []


def test_every_allowed_tool_has_a_bench_method():
    from server.agent.bench import Bench

    bench = Bench(skip_db=True)
    missing = [n for n in T.tool_names() if not callable(getattr(bench, n, None))]
    assert missing == [], f"no bench method for: {missing}"


def test_unknown_tool_is_denied():
    class B:
        pass

    out = T.dispatch(ToolCall(name="finish", args={"summary": "x" * 50, "success": True}), B())
    assert "error" in out  # no bench method


def test_out_of_range_parameters_are_rejected_with_an_explanation():
    T.reset_session_limits()
    call = ToolCall(name="simulate_hydrogel_assay",
                   args={"candidate": {}, "conditions": {"temperature_c": 500}})
    out = T._validate_args(call)
    assert out is not None and "parameter rejected" in out["error"]


def test_clinical_text_in_a_tool_argument_raises_rather_than_returning():
    T.reset_session_limits()
    call = ToolCall(name="highlight_step",
                   args={"stage": "report",
                         "detail": "recommended dose for this patient is 2 ml"})
    with pytest.raises(ClinicalOutputRefused):
        T._validate_args(call)


def test_simulation_cap_stops_a_runaway_session(monkeypatch):
    from shared import config

    monkeypatch.setattr(config.settings.__class__, "max_sim_calls_per_session", 3,
                        raising=False)
    T.reset_session_limits()
    hit = None
    for _ in range(50):
        out = T._validate_args(ToolCall(name="score_kinetics", args={"candidate": {}}))
        if out is not None:
            hit = out["error"]
            break
    assert hit is not None and "cap reached" in hit


def test_finish_requires_a_substantive_report():
    T.reset_session_limits()
    out = T._validate_args(ToolCall(name="finish", args={"summary": "done", "success": True}))
    assert out is not None and "real report" in out["error"]


def test_explain_mode_blocks_the_write_tools_at_validation_too():
    """Belt and braces: the schemas withhold them, and validation refuses
    them even if a model names one anyway."""
    T.reset_session_limits()
    out = T._validate_args(ToolCall(name="submit_candidate",
                                    args={"candidate_name": "x", "summary": "y"}),
                           mode="explain")
    assert out is not None and "explain mode" in out["error"]


def test_budget_and_tolerance_are_clamped_not_rejected():
    T.reset_session_limits()
    call = ToolCall(name="plan_next_experiment", args={"budget": 9999})
    assert T._validate_args(call) is None
    assert call.args["budget"] == 10
