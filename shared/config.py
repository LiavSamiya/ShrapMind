"""Centralized env-loaded config. Read once, import everywhere.

Same shape as voodo's shared/config.py. The secrets differ because the
surfaces differ: there is no Windows executor to authenticate here, and the
dashboard that needs gating is the biologists' review queue, since approving a
row there is what lets a claim reach the engine's answers.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal .env loader (no python-dotenv dep) — looks at repo root."""
    root = Path(__file__).resolve().parent.parent
    env = root / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    # Postgres + pgvector
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://shrapmind:shrapmind@localhost:5432/shrapmind"
    )

    # Backend / review dashboard
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "7870"))

    # Retrieval. A cosine similarity at or above this counts as "we have
    # answered this case before". Deliberately high: returning a loosely
    # similar past case as if it were this one is the failure mode that would
    # put the wrong enzyme in front of a reviewer.
    similarity_threshold: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.85"))

    # Embeddings. all-MiniLM-L6-v2 is 384-dim and matches schema.sql. If it is
    # not installed, client.py falls back to a lexical embedder of the same
    # width and says so — see the note there.
    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )

    # Review dashboard — FAIL CLOSED on missing password.
    reviewer_username: str = os.getenv("REVIEWER_USERNAME", "biologist")
    reviewer_password: str = os.getenv("REVIEWER_PASSWORD", "")

    # Admin, who can delete approved rows — FAIL CLOSED.
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")

    # Production mode — when set, dev conveniences are ignored.
    prod_mode: bool = os.getenv("SHRAPMIND_PROD", "").lower() in ("1", "true", "yes")


settings = Settings()


def _validate_secrets() -> None:
    """Refuse to start with empty or default-weak secrets in prod mode."""
    if not settings.prod_mode:
        return
    problems: list[str] = []
    if not settings.reviewer_password or settings.reviewer_password in (
        "biologist", "password", "admin", ""
    ):
        problems.append("REVIEWER_PASSWORD must be set to a strong value in SHRAPMIND_PROD=1")
    if not settings.admin_password or settings.admin_password in (
        "admin", "password", ""
    ):
        problems.append("ADMIN_PASSWORD must be set to a strong value in SHRAPMIND_PROD=1")
    if problems:
        print("[shrapmind:config] REFUSING TO START — fix .env:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        raise SystemExit(2)


_validate_secrets()
