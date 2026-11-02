"""Centralized input sanitization for anything that flows back into a prompt.

Adapted from voodo's shared/security.py. The injection markers are the same
problem — text written by one person, stored, and later fed to a model as
context — but the shell-command patterns voodo redacts are irrelevant here and
would only produce false positives, so they are gone.

Design rule, unchanged: FAIL CLOSED. If input does not match the strict
whitelist, reject rather than try to clean.

The reason this matters more than it looks: a reviewer's note is written by a
biologist, stored in Postgres, retrieved by similarity, and handed to a model
as "what an expert said about this case". That is a path from a text box to a
prompt, and every such path gets sanitized at the chokepoint, regardless of
how trusted the author is — a teammate's note can quote a paper that quotes
something hostile, and nobody along that chain is acting in bad faith.
"""
from __future__ import annotations

import re
import unicodedata

# Zero-width / bidi / format chars that attackers stuff into injection markers
# to slip past ASCII \b word-boundary regex (e.g. "i​gnore previous
# instructions"). NFKC-normalize first to fold full-width letters and
# ligatures down, then strip these explicitly.
_INVISIBLE_RE = re.compile(
    r"[­͏؜ᅟᅠ឴឵"
    r"᠋-᠎​-‏‪-‮⁠-⁤"
    r"⁦-⁯ㅤ︀-️﻿ﾠ￰-￻]"
)


def _normalize_for_match(s: str) -> str:
    """NFKC-fold + strip invisible / bidi chars so the injection regex sees
    the same string the human reads."""
    s = unicodedata.normalize("NFKC", s)
    return _INVISIBLE_RE.sub("", s)


# Aggressive by design: a false positive degrades one hint, a missed marker
# hijacks the model.
_INJECTION_PATTERNS = [
    r"\b(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above)\s+"
    r"(instructions?|prompts?|rules?|messages?)\b",
    r"\bsystem\s*(override|prompt|message|:)\b",
    r"\bassistant\s*:",
    r"\byou\s+must\b",
    r"\bnew\s+instruction[s]?\b",
    r"\bjailbreak\b",
    r"\b(developer|admin|maintenance)\s+mode\b",
    r"\b(bypass|override|disable)\s+(security|safeguards|filters)\b",
    r"\b(DAN|do\s+anything\s+now)\b",
    r"\bact\s+as\b",
    r"\bpretend\s+to\s+be\b",
    r"<\s*/?\s*(system|user|assistant|tool|think|tool_call)\s*>",
    r"##\s*(system|instruction|user instruction|tool result)",
    r"\[\s*(system|instruction|inst)\s*[:\]]",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

_REDACTED = "[redacted]"


def sanitize_for_prompt(text: str, max_len: int = 300) -> str:
    """Normalize, redact injection markers, collapse whitespace, truncate.

    Returns a string safe to place in model context and in the dashboard.
    """
    if not text:
        return ""
    s = _normalize_for_match(str(text))
    s = _INJECTION_RE.sub(_REDACTED, s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


_PMID_RE = re.compile(r"^\d{1,8}$")


def clean_pmids(values: list[str] | None, limit: int = 20) -> list[str]:
    """Keep only things shaped like a PMID.

    A PMID that survives this is still only well-formed, not real. Whether the
    paper exists and says what the reviewer thinks it says is settled by
    tools/verify_sources.py against NCBI, not here.
    """
    if not values:
        return []
    out: list[str] = []
    for v in values:
        v = str(v).strip().removeprefix("PMID:").strip()
        if _PMID_RE.match(v) and v not in out:
            out.append(v)
        if len(out) >= limit:
            break
    return out
