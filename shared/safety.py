"""Fail-closed validation. Four independent layers.

Design rule, borrowed verbatim from the system this is modelled on: every
function here is FAIL-CLOSED. When input looks wrong we REJECT it. We do NOT
try to "clean" it and carry on, because a cleaned-up injection attempt is
still an injection attempt and a clamped nonsense parameter still produces a
number that looks authoritative.

Layer 0  normalization        - NFKC + invisible-character stripping
Layer 1  prompt injection     - redact before anything re-enters model context
Layer 2  clinical-output gate - refuse dosing / indication / protocol output
Layer 3  numeric bounds       - every simulation parameter has a legal range

Layer 2 is the one that matters most here and it is the one with no
equivalent in a GUI-automation agent. This system models chemistry; it is not
licensed, qualified or validated to tell anyone what to do to a patient. The
gate is deliberately blunt and deliberately not overridable by a prompt.
"""
from __future__ import annotations

import re
import unicodedata

HINT_MAX_LEN = 400
CASE_MSG_MAX_LEN = 4000

# ---------------------------------------------------------------- layer 0

# Zero-width, bidi-override and format characters. These let "ignore" hide
# inside "ig<ZWSP>nore", so they come off before any pattern runs.
_INVISIBLE_RE = re.compile(
    r"[​-‏‪-‮⁠-⁤⁪-⁯﻿­]"
)


def _normalize_for_match(s: str) -> str:
    """NFKC-fold then strip invisibles, so full-width and zero-width
    obfuscations both collapse onto the plain ASCII form."""
    return _INVISIBLE_RE.sub("", unicodedata.normalize("NFKC", s))


# ---------------------------------------------------------------- layer 1

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?)",
    r"disregard\s+(all\s+)?(previous|prior|above|the)\s+\w+",
    r"forget\s+(everything|all|your)\s+\w+",
    r"you\s+are\s+now\s+(a|an|in)\b",
    r"new\s+(system\s+)?(instructions?|prompt|rules?)\s*[:\-]",
    r"</?(system|assistant|user|instructions?|tool)\s*>",
    r"^\s*(system|assistant)\s*:",
    r"\b(developer|debug|god|admin)\s+mode\b",
    r"\boverrid(e|ing)\s+(the\s+)?(safety|gate|check|guard)",
    r"\bdisable\s+(the\s+)?(safety|gates?|checks?|validation)",
    r"\bskip\s+(the\s+)?(safety|gates?|validation|mass\s*balance)",
    r"\bpretend\s+(you|to\s+be)\b",
    r"\bact\s+as\s+(a|an|if)\b",
    r"\brepeat\s+(your|the)\s+(system\s+)?prompt",
    r"\breveal\s+(your|the)\s+(system\s+)?(prompt|instructions?)",
    # shell / code execution, in case a record carries a payload
    r"\b(powershell|pwsh|/bin/(ba)?sh|cmd\.exe|subprocess|os\.system|eval\(|exec\()",
    r"\b(iex|invoke-expression|curl\s+-|wget\s+http)",
    r"\bimport\s+os\b",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def sanitize_for_prompt(text: str, max_len: int = HINT_MAX_LEN) -> str:
    """Make untrusted text safe to place back into model context.

    Applied to every DB hint, retrieved precedent, persisted summary and
    reviewer note - anything that was written by someone other than us and
    is about to be read by the model as if we had written it.
    """
    if not text:
        return ""
    s = text[:max_len]
    s = _normalize_for_match(s)
    s = _INJECTION_RE.sub("[redacted]", s)
    # Backticks and line separators let text break out of its block.
    s = s.replace("`", "'").replace(" ", " ").replace(" ", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def cap_case_message(text: str) -> str:
    """Hard cap + normalize the user's own case description."""
    return _normalize_for_match(text or "")[:CASE_MSG_MAX_LEN]


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION_RE.search(_normalize_for_match(text or "")))


# ---------------------------------------------------------------- layer 2


class ClinicalOutputRefused(ValueError):
    """Raised when text asks for, or constitutes, clinical direction.

    The agent loop treats this as a hard stop, not a retryable error. That is
    on purpose: given a soft failure a model will rephrase and try again.
    """


_CLINICAL_PATTERNS = [
    # dosing
    r"\b\d+\s*(mg|ml|mcg|µg|ug|iu|units?)\b.{0,40}\b(per|/)\s*(kg|dose|day|injection|patient)",
    r"\bdos(e|ing|age)\b.{0,40}\b(recommend|should|advise|protocol|schedule|regimen)",
    r"\brecommend(ed|s|ing)?\b.{0,30}\b(dose|dosage|volume|concentration)\b.{0,30}\bpatient",
    r"\binject\b.{0,40}\b(into|in)\s+(the\s+)?(patient|human|arm|leg|forearm|thigh|limb)",
    r"\binjection\s+volume\b.{0,40}\b(for|in)\s+(a\s+)?(patient|human)",
    # indication / eligibility
    r"\b(is|are)\s+(indicated|contraindicated)\s+(for|in)\b",
    r"\bthis\s+patient\s+(should|must|needs?\s+to)\b",
    r"\b(safe|ready|cleared|approved)\s+(for|to)\s+(use\s+in\s+)?(human|patient|clinical)\s+use",
    r"\btreatment\s+(protocol|schedule|plan)\s+for\s+(a\s+)?(patient|human)",
    r"\badminister\b.{0,30}\b(to|in)\s+(the\s+)?(patient|human)",
    # scheduling
    r"\b(every|each)\s+\d+\s*(hours?|days?|weeks?)\b.{0,40}\b(dose|injection|cycle|administ)",
]
_CLINICAL_RE = re.compile("|".join(_CLINICAL_PATTERNS), re.IGNORECASE | re.DOTALL)

# A short, explicit list of asks we refuse outright regardless of phrasing.
_CLINICAL_ASK_RE = re.compile(
    r"\b("
    r"what\s+dose|how\s+much\s+(should|do)\s+(i|we)\s+(inject|give|administer)"
    r"|prescrib\w+"
    r"|treatment\s+protocol\s+for\s+(me|my|a\s+patient)"
    r"|can\s+(i|we)\s+(inject|use)\s+this\s+(in|on)\s+(a\s+)?(patient|human|person|myself)"
    r")\b",
    re.IGNORECASE,
)

_SIMULATION_DISCLAIMER = (
    "Simulation hypothesis only - requires wet-lab validation. "
    "This system does not provide clinical guidance."
)


def check_clinical_output(text: str, *, where: str = "output") -> None:
    """Raise ClinicalOutputRefused if `text` reads as clinical direction.

    Run against both the model's own prose and every tool argument. Returns
    None on pass - it never rewrites, because a half-redacted dosing
    recommendation is more dangerous than a refused one.
    """
    if not text:
        return
    s = _normalize_for_match(text)
    if _CLINICAL_ASK_RE.search(s) or _CLINICAL_RE.search(s):
        raise ClinicalOutputRefused(
            f"clinical-output gate: refused {where}. This system models material "
            f"chemistry in simulation and must not produce dosing, indication, "
            f"eligibility or treatment-protocol content. {_SIMULATION_DISCLAIMER}"
        )


def simulation_disclaimer() -> str:
    return _SIMULATION_DISCLAIMER


# ---------------------------------------------------------------- layer 3

# Legal ranges for every simulation parameter the model is allowed to set.
# A hallucinated 500 degC assay would still produce a plausible-looking
# number, which is exactly why these are hard bounds and not suggestions.
BOUNDS: dict[str, tuple[float, float]] = {
    "temperature_c": (4.0, 45.0),
    "ph": (5.0, 8.5),
    # Up to one year. A retained fragment is a chronic problem and the brief
    # describes cyclical treatment over months, so a 90-day ceiling was cutting
    # off exactly the horizon the slower routes need to be judged over.
    "hours": (0.1, 8760.0),
    "timestep_h": (0.01, 6.0),
    "enzyme_uM": (0.001, 500.0),
    "mesh_nm": (1.0, 500.0),
    "gel_volume_ul": (10.0, 5000.0),
    "fragment_volume_mm3": (0.01, 5000.0),
    # Dispersed presentation: particle diameter. The lower bound is where
    # particles stop behaving as a solid phase and start behaving as a
    # nanoparticle with its own toxicology; the upper is where "particulate"
    # has become a fragment you could pick out individually.
    "particle_size_um": (0.1, 1000.0),
    "surface_area_mm2": (0.01, 20000.0),
    "serum_fraction": (0.0, 1.0),
    "n_samples": (1.0, 512.0),
    "top_k": (1.0, 25.0),
    "n_variants": (1.0, 25.0),
}


class ParameterOutOfRange(ValueError):
    pass


def validate_number(name: str, value: object) -> float:
    """Coerce and bounds-check one simulation parameter. Raises on failure."""
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ParameterOutOfRange(f"{name}: expected a number, got {value!r}") from None
    if v != v or v in (float("inf"), float("-inf")):  # NaN / inf
        raise ParameterOutOfRange(f"{name}: not a finite number ({value!r})")
    lo, hi = BOUNDS.get(name, (float("-inf"), float("inf")))
    if not (lo <= v <= hi):
        raise ParameterOutOfRange(f"{name}={v:g} is outside the legal range [{lo:g}, {hi:g}]")
    return v


def validate_params(params: dict[str, object]) -> dict[str, float]:
    """Validate every known key in `params`. Unknown keys pass through
    untouched - this checks numbers, it is not an arg-name allow-list
    (server/agent/tools.py does that)."""
    out: dict[str, float] = {}
    for k, v in params.items():
        if k in BOUNDS:
            out[k] = validate_number(k, v)
    return out


_IDENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-/()+]{0,80}$")


def validate_identifier(value: str, *, field: str = "name") -> str:
    """For free-text identifiers that end up in SQL parameters, filenames or
    log lines. Rejects rather than escapes."""
    s = _normalize_for_match(str(value or "")).strip()
    if not _IDENT_RE.match(s):
        raise ParameterOutOfRange(f"{field}: {value!r} is not a valid identifier")
    return s


def scrub_for_log(value: object, limit: int = 300) -> str:
    """Strip C0 controls and line separators so a tool argument cannot forge
    an extra line in the JSON audit log."""
    s = str(value)[:limit]
    s = "".join(ch for ch in s if ord(ch) >= 32 or ch == "\t")
    return s.replace(" ", " ").replace(" ", " ").replace("\u0085", " ")
