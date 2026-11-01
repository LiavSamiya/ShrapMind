"""LLM provider abstraction and streaming.

One `openai.OpenAI` client, base-URL switched. Any OpenAI-compatible
endpoint works: OpenAI, OpenRouter, Google's compat endpoint, a local
vLLM/Ollama server. Set LLM_MODEL and LLM_BASE_URL and nothing else changes.

Streaming is accumulated by hand because the two things we need from a
stream - reasoning text as it arrives, and tool calls assembled from
fragments arriving out of order - are not what the convenience helpers give
you.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from shared.config import settings
from shared.protocol import ToolCall

_PIPELINE = """\
The pipeline has ten stages. You do not have to use all of them, but you may
not skip a gate:

  INSPECT     read_passport
  CHARACTERIZE characterize_fragment    -> material family + confidence
  REACTION    define_reaction           -> bond class, products, FORBIDDEN products
              get_material_notes        -> what the real rate limit is
  RETRIEVE    retrieve_enzymes          -> candidate families (filter by material!)
              retrieve_precedents       -> what the literature does and does NOT prove
  GENERATE    propose_variants          -> sequence-level proposals
  PREDICT     predict_properties        -> developability scores
              score_kinetics            -> cheap shortlisting estimate
  SIMULATE    simulate_hydrogel_assay   -> the virtual experiment, with a band
              check_mass_balance        -> did the books close?
  GATE        run_safety_gates          -> REQUIRED. A failure ends the run.
  RANK        rank_candidates           -> multi-objective
              plan_next_experiment      -> what to measure in the wet lab
  REPORT      submit_candidate          -> queue for human review
              finish                    -> the report
"""

_SHARED_RULES = """\
WHAT YOU ARE
You are the design engine of ShrapMind. You take a case describing a solid
fragment retained in tissue, work out what it is made of, and search for an
enzyme candidate that could erode that specific material inside a hydrogel
that captures the products. You do this by running simulations.

WHAT YOU ARE NOT
You are not a clinician and this is not a medical system. You must never
produce a dose, an injection volume for a person, an indication, an
eligibility judgement, a treatment schedule, or any statement that a
candidate is safe, validated or ready for use in a patient. If the case asks
for any of those, refuse that part explicitly and continue with the
chemistry. A hard gate enforces this; arguing with it wastes the run.

Everything you output is a SIMULATION HYPOTHESIS requiring wet-lab
validation. Say so in your report. Not as a disclaimer bolted on the end -
as the actual status of the finding.

HOW TO BE USEFUL RATHER THAN IMPRESSIVE
- Name the constraint that actually binds. For cellulose it is accessibility,
  not turnover. For iron it is ion capture, not rate. A high k_cat quoted
  without its assay conditions is not evidence.
- Carry uncertainty through. You get a 5-95 percentile band, not a number.
  If the band spans an order of magnitude, the finding is "we need this
  measurement", and that is a legitimate and valuable answer.
- Report what the precedents do NOT prove. Every precedent record carries
  that field. Use it.
- A no-go is a result. If the material has no credible route, or the gates
  fail, say that clearly and say why. Do not downgrade to a weak candidate
  to have something to show.
- Never invent kinetic numbers. Use what retrieval returns. If retrieval
  returns nothing, say so.
- Avoid buzzwords. Write for a working scientist who will ask you which
  number you are basing that on.

THE GATES
run_safety_gates is mandatory before submit_candidate or finish(success=true).
If a gate fails, the run stops and you report the failure. Do not re-run the
same candidate with different wording, do not route around the gate, and do
not describe a gate failure as a minor issue. The gates are: mass balance,
fragmentation, free product, capture efficiency, forbidden products,
predictive confidence, meaningful erosion, tissue off-target, anatomical
tier, material identification.
"""

SYSTEM_PROMPT_RUN = f"""{_SHARED_RULES}
MODE: RUN
You execute the pipeline: retrieve, propose, simulate, gate, rank, report.

{_PIPELINE}
Work in order. Each turn you receive the full bench state - the passport, the
reaction spec, the candidate table, every assay result and every gate
verdict. Judge from that state, not from your memory of what you intended:
the actions you took may have failed, been rejected or been clamped.

Call several tools in one turn when they are independent. Simulate a
shortlist, not everything you proposed.

Finish with a report that a reviewer could act on: the chosen candidate, its
erosion band and conditions, which gates passed with their numbers, what the
precedents do not establish, and the ranked list of experiments to run next.
"""

SYSTEM_PROMPT_EXPLAIN = f"""{_SHARED_RULES}
MODE: EXPLAIN
You do NOT run simulations and you do NOT write to the library. The tools
that would do either are withheld from you in this mode.

Your job is to teach the pipeline on this specific case. Walk the stages with
highlight_step, and for each one say what would happen, what input it needs,
what could go wrong, and what the output would mean. Use read_passport,
characterize_fragment, define_reaction, get_material_notes,
retrieve_enzymes, retrieve_precedents, predict_properties and rank_candidates
freely - they are cheap and they are read-only.

{_PIPELINE}
Be concrete about this case's material, not generic about chemistry. If you
reach a point where only a simulation could answer the question, say exactly
which simulation and what it would tell us - then stop, rather than guessing
the result.
"""


def build_turn_message(body: str) -> dict[str, Any]:
    """One user message carrying the task and the current bench state."""
    return {"role": "user", "content": [{"type": "text", "text": body}]}


class _StreamedFn:
    __slots__ = ("name", "arguments")

    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _StreamedToolCall:
    """Re-shapes accumulated deltas so the streaming and non-streaming paths
    both read `tc.function.name` / `tc.function.arguments`."""

    __slots__ = ("function",)

    def __init__(self, name: str, arguments: str) -> None:
        self.function = _StreamedFn(name, arguments)


class LLMClient:
    def __init__(self, mock: bool = False, mode: str = "run") -> None:
        self.mock = mock
        self.mode = mode
        self._mock_impl: Any = None
        if mock:
            from server.agent.mock_llm import MockLLM

            self._mock_impl = MockLLM()
            self._client = None
            return

        import openai

        base_url = settings.llm_base_url
        api_key = settings.llm_api_key
        model = settings.llm_model.lower()
        if "gemini" in model and "/" not in model and settings.gemini_api_key:
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
            api_key = settings.gemini_api_key
        elif not base_url:
            base_url = "https://openrouter.ai/api/v1"
            api_key = settings.openrouter_api_key or settings.llm_api_key
        self._client = openai.OpenAI(base_url=base_url, api_key=api_key or "EMPTY")

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT_EXPLAIN if self.mode == "explain" else SYSTEM_PROMPT_RUN

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        on_thought_delta: Callable[[str], None] | None = None,
        interrupt_event: Any = None,
        max_retries: int = 3,
    ) -> tuple[str, list[ToolCall]]:
        """One turn. Returns (thought_text, tool_calls)."""
        if self._mock_impl is not None:
            return self._mock_impl.chat(messages, tools)

        import httpx
        import openai

        is_thinking = "thinking" in settings.llm_model.lower()
        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                return self._chat_once(messages, tools, on_thought_delta,
                                       interrupt_event, is_thinking)
            except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout,
                    openai.APIConnectionError, openai.APIError) as e:
                last_err = e
                if attempt < max_retries - 1:
                    time.sleep(2)
        raise RuntimeError(f"LLM unreachable after {max_retries} attempts: {last_err}")

    def _chat_once(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        on_thought_delta: Callable[[str], None] | None,
        interrupt_event: Any,
        is_thinking: bool,
    ) -> tuple[str, list[ToolCall]]:
        kwargs: dict[str, Any] = {
            "model": settings.llm_model,
            "messages": messages,
            "tools": tools,
            "max_tokens": 4096 if is_thinking else 1536,
            "temperature": 0.2,
            "stream": True,
        }
        if is_thinking:
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": True}}

        text_parts: list[str] = []
        tc_acc: dict[int, dict[str, str]] = {}
        stream = self._client.chat.completions.create(**kwargs)  # type: ignore[union-attr]
        for chunk in stream:
            if interrupt_event is not None and interrupt_event.is_set():
                break
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            # Reasoning arrives under different names across providers.
            piece = (getattr(delta, "reasoning_content", None)
                     or getattr(delta, "reasoning", None)
                     or getattr(delta, "content", None))
            if piece:
                text_parts.append(piece)
                if on_thought_delta is not None:
                    on_thought_delta(piece)
            for tc in (getattr(delta, "tool_calls", None) or []):
                idx = getattr(tc, "index", 0) or 0
                slot = tc_acc.setdefault(idx, {"name": "", "args": ""})
                fn = getattr(tc, "function", None)
                if fn is not None:
                    if getattr(fn, "name", None):
                        slot["name"] = fn.name
                    if getattr(fn, "arguments", None):
                        slot["args"] += fn.arguments

        thought = "".join(text_parts).strip()
        calls: list[ToolCall] = []
        for idx in sorted(tc_acc):
            slot = tc_acc[idx]
            if not slot["name"]:
                continue
            try:
                args = json.loads(slot["args"]) if slot["args"].strip() else {}
            except ValueError:
                # A truncated or malformed argument blob: skip the call rather
                # than guessing. The loop will push back and the model retries.
                continue
            if not isinstance(args, dict):
                continue
            try:
                calls.append(ToolCall(name=slot["name"], args=args))  # type: ignore[arg-type]
            except Exception:  # noqa: BLE001 - unknown tool name
                continue
        return thought, calls
