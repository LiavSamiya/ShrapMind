import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "client" / "worker"))
os.environ.setdefault("WORKER_TOKEN", "x" * 32)

import pytest  # noqa: E402


@pytest.fixture
def fake_worker(monkeypatch):
    """Route bridge.call_sync straight into the engines module, in-process.

    Lets the whole loop be tested without a WebSocket, a worker process or a
    database - which is the same property that makes the mock demo possible.
    """
    import engines as E

    import server.agent.bench as bench_mod
    import server.app.bridge as bridge_mod

    class FakeBridge:
        def is_connected(self, client_id="default"):
            return True

        def call_sync(self, client_id, name, args=None, timeout=60.0):
            fn = getattr(E, name, None)
            if fn is None:
                raise RuntimeError(f"unknown tool {name}")
            return fn(**(args or {}))

    fb = FakeBridge()
    monkeypatch.setattr(bridge_mod, "bridge", fb)
    monkeypatch.setattr(bench_mod, "bridge", fb)
    return fb
