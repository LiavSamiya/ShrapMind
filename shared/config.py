"""Centralized env-loaded config. Read once, import everywhere."""
from __future__ import annotations

import os
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal .env loader (no python-dotenv dep) - looks at repo root."""
    root = Path(__file__).resolve().parent.parent
    env = root / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        # Real environment wins over the file.
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

_PROD = os.getenv("SHRAPMIND_PROD", "").lower() in ("1", "true", "yes")


def _bootstrap_dev_token() -> None:
    """Mint a dev WORKER_TOKEN rather than leaving the socket open.

    Fail-safe by default: an empty token must never mean "accept anyone".
    In prod we leave it empty so _validate_secrets() can refuse to boot.
    """
    if _PROD or os.getenv("WORKER_TOKEN"):
        return
    token = secrets.token_hex(24)
    os.environ["WORKER_TOKEN"] = token
    print(
        f"[config] WORKER_TOKEN not set - minted a dev token: {token}\n"
        f"[config] Start the worker with: --token {token}",
        file=sys.stderr,
    )


_bootstrap_dev_token()


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    """Defaults are evaluated at class-definition time, so Settings()
    snapshots the environment once. Mutating os.environ later has no effect -
    that is deliberate: one process, one configuration.
    """

    # LLM provider - OpenAI or any compatible API
    llm_base_url: str | None = os.getenv("LLM_BASE_URL")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")

    # Postgres + pgvector
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://shrapmind:shrapmind@localhost:5432/shrapmind"
    )

    # Simulation worker link.
    #
    # The worker opens a WebSocket to us at /worker, so the backend never
    # needs to know the worker's IP and nothing has to be port-forwarded.
    # WORKER_TOKEN is the shared secret gating that connection; both sides
    # need the same value. BACKEND_WS_URL is only read by the worker process.
    worker_token: str = os.getenv("WORKER_TOKEN", "")

    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = _i("APP_PORT", 7860)

    # Agent loop
    agent_max_steps: int = _i("AGENT_MAX_STEPS", 15)
    similarity_threshold: float = _f("SIMILARITY_THRESHOLD", 0.85)

    # Per-session caps. A design loop that calls the simulator 200 times is
    # either stuck or being abused; either way we stop it.
    max_sim_calls_per_session: int = _i("SHRAPMIND_MAX_SIM_CALLS", 40)
    max_candidates_per_session: int = _i("SHRAPMIND_MAX_CANDIDATES", 25)

    # Reviewer dashboard (scientific approval gate)
    reviewer_username: str = os.getenv("REVIEWER_USERNAME", "reviewer")
    reviewer_password: str = os.getenv("REVIEWER_PASSWORD", "")
    admin_username: str = os.getenv("ADMIN_USERNAME", "admin")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")

    prod_mode: bool = _PROD


settings = Settings()

_WEAK = {"", "password", "changeme", "admin", "shrapmind", "123456", "secret"}


def _validate_secrets() -> None:
    """In prod, refuse to boot on a weak configuration. Dev stays permissive."""
    if not settings.prod_mode:
        return
    problems: list[str] = []
    if not (settings.llm_api_key or settings.openrouter_api_key or settings.gemini_api_key):
        problems.append("no LLM API key set (LLM_API_KEY / OPENROUTER_API_KEY / GEMINI_API_KEY)")
    if len(settings.worker_token) < 24:
        problems.append("WORKER_TOKEN missing or shorter than 24 chars")
    if settings.reviewer_password.lower() in _WEAK:
        problems.append("REVIEWER_PASSWORD is empty or weak")
    if settings.admin_password.lower() in _WEAK:
        problems.append("ADMIN_PASSWORD is empty or weak")
    if problems:
        print("[config] refusing to start in prod mode:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        raise SystemExit(2)


_validate_secrets()
