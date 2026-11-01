"""ShrapMind simulation worker - thin reverse-WebSocket client.

Pure transport plus reflection. It knows nothing about the design loop: it
receives {"req_id", "name", "args"}, looks the name up in the engines module
namespace, runs it off the event loop, and replies
{"req_id", "ok", "result"} or {"req_id", "ok": false, "error"}.

WHY IT DIALS OUT
    The worker opens the connection to the backend, never the reverse. So the
    machine with the compute on it - a GPU box, a lab workstation, a laptop
    behind NAT - needs no inbound port, no port-forwarding and no VPN. The
    backend never needs to know where the worker is. The same property is
    what lets one backend fan work out to several workers keyed by client_id.

    The trade-off is that the token in WORKER_TOKEN is the only thing
    standing between the backend and anyone who can reach it, which is why
    shared/config.py refuses to boot in prod without a real one.

Run:
    python -m client.worker.main --backend ws://localhost:7860 --token <tok>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import traceback
from typing import Any

try:
    import websockets
except ImportError:  # pragma: no cover
    print("pip install -r client/worker/requirements.txt", file=sys.stderr)
    raise

# Allow both `python -m client.worker.main` (repo root on PYTHONPATH) and
# `python main.py` from inside client/worker/.
try:
    from client.worker import engines
except ImportError:  # pragma: no cover
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import engines  # type: ignore[no-redef]

from shared.config import settings

# Results whose full payload is noise in the log - print key names only.
_NOISY_RESULTS = {"simulate_hydrogel_assay", "propose_variants", "engine_info"}

_MAX_FRAME = 16 * 1024 * 1024  # assay traces, not screenshots


def _fmt_args(name: str, args: dict[str, Any]) -> str:
    if not args:
        return ""
    out = []
    for k, v in args.items():
        if isinstance(v, (dict, list)):
            out.append(f"{k}=<{type(v).__name__}:{len(v)}>")
        else:
            s = str(v)
            out.append(f"{k}={s[:40]}")
    return " ".join(out)


def _fmt_result(name: str, result: Any) -> str:
    if name in _NOISY_RESULTS and isinstance(result, dict):
        return "{" + ", ".join(sorted(result)[:8]) + "}"
    s = str(result)
    return s if len(s) <= 160 else s[:160] + "..."


async def _handle_one(ws: Any) -> None:
    """Serve requests until the socket closes."""
    async for raw in ws:
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            print(f"[worker] dropped malformed frame ({len(raw)} bytes)", file=sys.stderr)
            continue
        req_id = msg.get("req_id")
        name = msg.get("name")
        args = msg.get("args") or {}
        if not isinstance(args, dict):
            await ws.send(json.dumps({"req_id": req_id, "ok": False,
                                      "error": "args must be an object"}))
            continue

        # The module namespace IS the dispatch table. A leading underscore is
        # never callable from the wire.
        fn = getattr(engines, str(name), None) if not str(name).startswith("_") else None
        if fn is None or not callable(fn):
            await ws.send(json.dumps({"req_id": req_id, "ok": False,
                                      "error": f"unknown tool {name!r}"}))
            continue

        print(f"[worker] -> {name} {_fmt_args(str(name), args)}")
        try:
            # Engines are synchronous and CPU-bound; keep the socket responsive.
            result = await asyncio.to_thread(fn, **args)
            print(f"[worker] <- {name} {_fmt_result(str(name), result)}")
            await ws.send(json.dumps({"req_id": req_id, "ok": True, "result": result},
                                     default=str))
        except TypeError as e:
            await ws.send(json.dumps({"req_id": req_id, "ok": False,
                                      "error": f"bad args for {name}: {e}"}))
        except Exception as e:  # noqa: BLE001 - the wire needs every failure
            if os.getenv("SHRAPMIND_DEBUG"):
                traceback.print_exc()
            await ws.send(json.dumps({"req_id": req_id, "ok": False,
                                      "error": f"{type(e).__name__}: {e}"}))


async def _run(backend_url: str, token: str, client_id: str = "default") -> None:
    """Dial out, serve, and reconnect forever with exponential backoff."""
    url = f"{backend_url.rstrip('/')}/worker?token={token}&client_id={client_id}"
    shown = url.replace(token, token[:6] + "...") if token else url
    backoff = 1.0
    while True:
        try:
            print(f"[worker] connecting to {shown}")
            async with websockets.connect(url, max_size=_MAX_FRAME, ping_interval=20) as ws:
                print("[worker] connected")
                backoff = 1.0
                # Announce what this worker can actually do, so the backend can
                # report it on /api/worker rather than assuming a version.
                await ws.send(json.dumps({"type": "hello",
                                          "info": engines.engine_info()}, default=str))
                await _handle_one(ws)
            print("[worker] backend closed the connection")
        except (OSError, websockets.exceptions.ConnectionClosed) as e:
            print(f"[worker] link down ({type(e).__name__}: {e})", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"[worker] unexpected: {type(e).__name__}: {e}", file=sys.stderr)
            if os.getenv("SHRAPMIND_DEBUG"):
                traceback.print_exc()
        print(f"[worker] reconnecting in {backoff:.0f}s")
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 15.0)


def _print_startup_diag() -> None:
    info = engines.engine_info()
    print(f"[worker] engine {info['engine_version']}  numpy={info['numpy']}  mock={info['mock']}")
    print(f"[worker] materials: {', '.join(info['materials'])}")
    print(f"[worker] no-go:     {', '.join(info['no_go_materials'])}")
    if info["numpy"] is None:
        print("[worker] WARNING: numpy missing - simulate_hydrogel_assay will fail. "
              "pip install -r client/worker/requirements.txt", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="ShrapMind simulation worker")
    ap.add_argument("--backend", default=os.getenv("BACKEND_WS_URL", "ws://localhost:7860"),
                    help="backend WebSocket base URL")
    ap.add_argument("--token", default=settings.worker_token, help="shared WORKER_TOKEN")
    ap.add_argument("--client-id", default=os.getenv("WORKER_CLIENT_ID", "default"),
                    help="identity this worker registers under")
    args = ap.parse_args()

    if not args.token:
        print("[worker] no token. Set WORKER_TOKEN or pass --token.", file=sys.stderr)
        return 2

    _print_startup_diag()
    try:
        asyncio.run(_run(args.backend, args.token, args.client_id))
    except KeyboardInterrupt:
        print("\n[worker] stopped")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
