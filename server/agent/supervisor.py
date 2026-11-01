"""LLM-as-judge on finish: does the report actually support its conclusion?

Checks the four things a reviewer would check first, and the ones a model
most often skips when it is pleased with itself:
  1. does it cite concrete numbers from the assay, or just adjectives
  2. does it name which gates passed
  3. does it state what the evidence does NOT establish
  4. does it avoid claiming clinical validity

FAILS OPEN. If the provider is unconfigured or the call throws, the run is
approved with its original summary. A verification step that can block a
finished run on an infrastructure hiccup is worse than no verification step.
"""
from __future__ import annotations

import json
from typing import Any

from shared.config import settings

_PROMPT = """You are reviewing the final report of a simulation run that searched for an
enzyme candidate to erode a retained material fragment.

Approve only if ALL of these hold:
1. It cites at least one concrete quantity from the simulation (an erosion rate, a
   band, a captured fraction, a mass-balance residual).
2. It states which safety gates passed, or that they did.
3. It states at least one thing the evidence does NOT establish.
4. It does NOT claim the candidate is clinically safe, validated, approved, or
   ready for use in a person, and does not give dosing or treatment direction.

If you reject, your feedback must be a rewritten report that fixes the gap while
keeping every factual claim from the original. Do not invent numbers.

Reply with JSON only: {"approved": true|false, "feedback": "..."}

GOAL
%(goal)s

REPORT
%(summary)s
"""


def verify_finish(goal: str, agent_summary: str,
                  bench_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Returns {"approved": bool, "feedback": str}."""
    key = (settings.llm_api_key or settings.openrouter_api_key
           or settings.gemini_api_key)
    if not key:
        return {"approved": True, "feedback": agent_summary}
    try:
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
        client = openai.OpenAI(base_url=base_url, api_key=api_key or "EMPTY")

        resp = client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": _PROMPT % {
                "goal": goal[:2000], "summary": agent_summary[:6000]}}],
            temperature=0.0,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        return {
            "approved": bool(data.get("approved", True)),
            "feedback": str(data.get("feedback") or agent_summary),
        }
    except Exception:  # noqa: BLE001 - fail open, deliberately
        return {"approved": True, "feedback": agent_summary}
