"""Reverse-WebSocket RPC to the simulation worker.

The worker dials in to /worker. We hold the socket and call *out* over it,
correlating replies by req_id against a dict of asyncio Futures. The agent
loop is synchronous and runs in a thread, so it uses `call_sync`, which
hops onto the event loop and blocks the calling thread until the reply lands.

Envelope on the wire:
    request   {"req_id": int, "name": str, "args": dict}
    response  {"req_id": int, "ok": true,  "result": any}
            | {"req_id": int, "ok": false, "error": str}

`call_sync` unwraps that: it returns `result`, or raises RuntimeError(error).
Callers never see the envelope.
"""
from __future__ import annotations

import asyncio
import itertools
from typing import Any


class WorkerConnection:
    """One live worker socket plus its in-flight calls."""

    def __init__(self, ws: Any, loop: asyncio.AbstractEventLoop) -> None:
        self.ws = ws
        self.loop = loop
        self.pending: dict[int, asyncio.Future] = {}
        self.ids = itertools.count(1)
        self.lock = asyncio.Lock()  # serialize sends on one socket
        self.info: dict[str, Any] = {}


class WorkerBridge:
    """Registry of connected workers, keyed by client_id."""

    def __init__(self) -> None:
        self._clients: dict[str, WorkerConnection] = {}

    # ------------------------------------------------------------------ state

    def is_connected(self, client_id: str = "default") -> bool:
        return client_id in self._clients

    def connected_ids(self) -> list[str]:
        return sorted(self._clients)

    def info(self, client_id: str = "default") -> dict[str, Any]:
        conn = self._clients.get(client_id)
        return dict(conn.info) if conn else {}

    # ------------------------------------------------------------------ serve

    async def serve(self, ws: Any, loop: asyncio.AbstractEventLoop,
                    client_id: str = "default") -> None:
        """Own this socket until it closes. Last writer wins.

        A reconnecting worker replaces the stale entry rather than being
        refused - otherwise a worker that lost its link could never get back
        in without a backend restart.
        """
        prior = self._clients.get(client_id)
        if prior is not None:
            try:
                await prior.ws.close(code=1000, reason="replaced by a new worker")
            except Exception:  # noqa: BLE001
                pass
        conn = WorkerConnection(ws, loop)
        self._clients[client_id] = conn
        try:
            while True:
                raw = await ws.receive_text()
                await self._on_message(conn, raw)
        except Exception:  # noqa: BLE001 - normal disconnects land here too
            pass
        finally:
            if self._clients.get(client_id) is conn:
                del self._clients[client_id]
            # Nothing is going to answer these now. Fail them loudly rather
            # than leaving the agent thread blocked on a dead socket.
            for fut in list(conn.pending.values()):
                if not fut.done():
                    fut.set_exception(RuntimeError("simulation worker disconnected"))
            conn.pending.clear()

    async def _on_message(self, conn: WorkerConnection, raw: Any) -> None:
        import json

        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            return
        if msg.get("type") == "hello":
            conn.info = msg.get("info") or {}
            return
        req_id = msg.get("req_id")
        fut = conn.pending.pop(req_id, None)
        if fut is not None and not fut.done():
            fut.set_result(msg)

    # ------------------------------------------------------------------- call

    async def _call_async(self, client_id: str, name: str, args: dict[str, Any],
                          timeout: float) -> dict[str, Any]:
        conn = self._clients.get(client_id)
        if conn is None:
            raise RuntimeError(f"no simulation worker connected as {client_id!r}")
        import json

        req_id = next(conn.ids)
        fut: asyncio.Future = conn.loop.create_future()
        conn.pending[req_id] = fut
        try:
            async with conn.lock:
                await conn.ws.send_text(json.dumps(
                    {"req_id": req_id, "name": name, "args": args}, default=str))
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            conn.pending.pop(req_id, None)

    def call_sync(self, client_id: str, name: str, args: dict[str, Any] | None = None,
                  timeout: float = 60.0) -> Any:
        """Call a worker tool from a synchronous thread.

        The agent loop is sync by design (it is far easier to reason about a
        step-by-step loop than an async one), so this is the single seam
        between it and the event loop.
        """
        conn = self._clients.get(client_id)
        if conn is None:
            raise RuntimeError(f"no simulation worker connected as {client_id!r}")
        fut = asyncio.run_coroutine_threadsafe(
            self._call_async(client_id, name, args or {}, timeout), conn.loop)
        # Give the coroutine's own wait_for a chance to fire first, so a
        # timeout is reported as a timeout and not as a thread-level stall.
        reply = fut.result(timeout=timeout + 5)
        if not reply.get("ok"):
            raise RuntimeError(reply.get("error") or "worker call failed")
        return reply.get("result")


# Module-level singleton, imported by server/app/main.py and
# server/agent/bench.py.
bridge = WorkerBridge()
