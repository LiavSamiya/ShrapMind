"""FastAPI backend: the design console, the reviewer dashboard, and the two
WebSocket endpoints.

THE SEAM THAT MATTERS is _run_one_case(): the design loop is synchronous and
runs in asyncio.to_thread, pushing events onto an asyncio.Queue through a
thread-safe shim, while this coroutine drains the queue and broadcasts. That
is what lets a straightforward sync loop drive a live streaming UI without
either side knowing about the other.

Pause / resume / stop are threading.Event flips on shared session state, not
task cancellation. Any connected socket can steer the one in-flight run, and
the loop polls the events at its own checkpoints - so it always stops
somewhere it can explain, rather than wherever the cancellation landed.
"""
from __future__ import annotations

import asyncio
import collections
import hmac
import os
import threading
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server.app.bridge import bridge
from shared.config import settings
from shared.protocol import AgentEvent, CaseMessage
from shared.safety import cap_case_message

STATIC_DIR = Path(__file__).parent / "static"
_DONE = object()

app = FastAPI(title="ShrapMind", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

security = HTTPBasic()


# --------------------------------------------------------------- session state


class ClientState:
    """Everything one console session owns."""

    def __init__(self) -> None:
        self.subscribers: set[WebSocket] = set()
        self.session: dict[str, threading.Event | None] = {
            "cancel": None, "interrupt": None, "sim_approved": None}
        self.current_task: asyncio.Task | None = None
        self.mode: str = "run"


_clients: dict[str, ClientState] = collections.defaultdict(ClientState)


async def _broadcast(client_id: str, event: AgentEvent) -> None:
    state = _clients[client_id]
    payload = event.model_dump()
    dead: list[WebSocket] = []
    for ws in list(state.subscribers):
        try:
            await ws.send_json(payload)
        except Exception:  # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        state.subscribers.discard(ws)


# --------------------------------------------------------------- auth


def _check(credentials: HTTPBasicCredentials, user: str, password: str) -> None:
    """Fail closed: an unset password is a 503, never an open door."""
    if not password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This dashboard is disabled until its password is configured "
                   "in .env.")
    ok_user = hmac.compare_digest(credentials.username.encode(), user.encode())
    ok_pass = hmac.compare_digest(credentials.password.encode(), password.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized",
            headers={"WWW-Authenticate": "Basic"})


def verify_reviewer(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    _check(credentials, settings.reviewer_username, settings.reviewer_password)
    return credentials.username


def verify_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """Separate credential from the reviewer. The system this is modelled on
    validates an admin password at startup and then never enforces it; here
    the admin routes actually check it."""
    _check(credentials, settings.admin_username, settings.admin_password)
    return credentials.username


# --------------------------------------------------------------- pages


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": True,
        "workers": bridge.connected_ids(),
        "consoles": sum(len(s.subscribers) for s in _clients.values()),
        "mock_llm": bool(_flag("MOCK_LLM")),
        "mock_agent": bool(_flag("MOCK_AGENT")),
        "skip_db": bool(_flag("SKIP_DB")),
    }
    if not _flag("SKIP_DB"):
        try:
            from server.db.client import db_health

            out["db"] = db_health()
        except Exception as e:  # noqa: BLE001
            out["db"] = {"ok": False, "error": str(e)}
    return out


@app.get("/review")
async def review_page(_: str = Depends(verify_reviewer)) -> FileResponse:
    return FileResponse(STATIC_DIR / "review.html")


# --------------------------------------------------------------- api


def _db_unavailable(e: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": "knowledge base unavailable", "detail": str(e)})


@app.get("/api/library")
async def api_library(_: str = Depends(verify_reviewer)) -> Any:
    try:
        from server.db.client import get_validated_library

        return {"library": get_validated_library(limit=200)}
    except Exception as e:  # noqa: BLE001
        return _db_unavailable(e)


class _SubmitBody(BaseModel):
    candidate_name: str
    summary: str
    rationale: str = ""
    material_family: str = ""
    type: str = "add"
    library_id: str | None = None


@app.post("/api/pending-candidates")
async def api_submit(body: _SubmitBody, user: str = Depends(verify_reviewer)) -> Any:
    try:
        from server.db.client import submit_pending_candidate

        return submit_pending_candidate(
            body.type, body.candidate_name, body.summary,
            material_family=body.material_family, rationale=body.rationale,
            library_id=body.library_id, submitted_by=user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        return _db_unavailable(e)


@app.get("/api/pending-candidates")
async def api_pending(_: str = Depends(verify_reviewer)) -> Any:
    try:
        from server.db.client import get_pending_candidates

        return {"pending": get_pending_candidates()}
    except Exception as e:  # noqa: BLE001
        return _db_unavailable(e)


@app.delete("/api/pending-candidates/{change_id}")
async def api_cancel(change_id: str, _: str = Depends(verify_reviewer)) -> Any:
    try:
        from server.db.client import cancel_pending_candidate

        if not cancel_pending_candidate(change_id):
            raise HTTPException(status_code=404,
                                detail="not found, or already reviewed")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        return _db_unavailable(e)


class _ReviewBody(BaseModel):
    reviewer_note: str | None = None


@app.put("/api/admin/pending-candidates/{change_id}/approve")
async def api_approve(change_id: str, body: _ReviewBody,
                      user: str = Depends(verify_admin)) -> Any:
    try:
        from server.db.client import approve_pending_candidate

        res = approve_pending_candidate(change_id, body.reviewer_note, approved_by=user)
        if not res.get("ok"):
            # A gate failure reaching this endpoint is a 409, not a 500: the
            # request was well-formed, the state forbids it.
            raise HTTPException(status_code=409, detail=res.get("error"))
        return res
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        return _db_unavailable(e)


@app.put("/api/admin/pending-candidates/{change_id}/reject")
async def api_reject(change_id: str, body: _ReviewBody,
                     _: str = Depends(verify_admin)) -> Any:
    try:
        from server.db.client import reject_pending_candidate

        if not reject_pending_candidate(change_id, body.reviewer_note):
            raise HTTPException(status_code=404,
                                detail="not found, or already reviewed")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        return _db_unavailable(e)


@app.get("/api/worker")
async def api_worker() -> Any:
    return {"connected": bridge.connected_ids(),
            "info": {cid: bridge.info(cid) for cid in bridge.connected_ids()}}


# --------------------------------------------------------------- websockets


def _flag(name: str) -> bool:
    """Dev shortcuts, force-disabled in prod so a stray env var in a deploy
    cannot quietly downgrade it to the scripted demo."""
    if settings.prod_mode:
        return False
    return os.getenv(name, "").lower() in ("1", "true", "yes")


@app.websocket("/worker")
async def ws_worker(ws: WebSocket) -> None:
    """The simulation worker dials in here."""
    token = ws.query_params.get("token", "")
    client_id = ws.query_params.get("client_id", "default")
    if not settings.worker_token:
        # Server misconfigured: refuse rather than accept anyone.
        await ws.close(code=4500)
        return
    if not hmac.compare_digest(token.encode(), settings.worker_token.encode()):
        await ws.close(code=4401)
        return
    await ws.accept()
    print(f"[app] worker connected as {client_id!r}")
    try:
        await bridge.serve(ws, asyncio.get_running_loop(), client_id)
    finally:
        print(f"[app] worker {client_id!r} disconnected")


@app.websocket("/ws")
async def ws_console(ws: WebSocket) -> None:
    """The browser console."""
    client_id = ws.query_params.get("client_id", "default")
    await ws.accept()
    state = _clients[client_id]
    state.subscribers.add(ws)
    await ws.send_json(AgentEvent(kind="status", payload={
        "msg": "connected",
        "worker_connected": bridge.is_connected(client_id),
        "mode": state.mode,
    }).model_dump())
    try:
        while True:
            msg = await ws.receive_json()
            await _handle_console_message(msg, ws, client_id, state)
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        print(f"[app] console socket error: {e}")
    finally:
        await _on_subscriber_drop(ws, state)


async def _handle_console_message(msg: dict[str, Any], ws: WebSocket,
                                  client_id: str, state: ClientState) -> None:
    kind = str(msg.get("type", ""))

    if kind == "stop":
        if state.session["cancel"] is not None:
            state.session["cancel"].set()
        if state.session["interrupt"] is not None:
            state.session["interrupt"].clear()
        return

    if kind == "pause":
        if state.session["interrupt"] is not None:
            state.session["interrupt"].set()
        return

    if kind == "resume":
        if state.session["interrupt"] is not None:
            state.session["interrupt"].clear()
        return

    if kind == "approve_simulation":
        if state.session["sim_approved"] is not None:
            state.session["sim_approved"].set()
        return

    if kind == "set_mode":
        mode = str(msg.get("mode", "run"))
        if mode in ("run", "explain"):
            state.mode = mode
            await _broadcast(client_id, AgentEvent(kind="mode_change",
                                                   payload={"mode": mode}))
        return

    if kind == "feedback":
        try:
            from server.db.client import save_feedback

            save_feedback(str(msg.get("rating", "")), msg.get("success"),
                          msg.get("summary"), source="browser")
        except Exception as e:  # noqa: BLE001
            print(f"[app] feedback not saved: {e}")
        return

    if kind != "message":
        return

    # ------------------------------------------------- start a run

    text = cap_case_message(str(msg.get("text", "")))
    if not text.strip():
        return
    mode = str(msg.get("mode", state.mode))
    if mode not in ("run", "explain"):
        mode = "run"
    state.mode = mode

    task = state.current_task
    if task is not None and not task.done():
        paused = (state.session["interrupt"] is not None
                  and state.session["interrupt"].is_set())
        if paused:
            # A new case while paused means "forget that one" - stop it and
            # start fresh rather than resuming into stale state.
            if state.session["cancel"] is not None:
                state.session["cancel"].set()
            if state.session["interrupt"] is not None:
                state.session["interrupt"].clear()
            try:
                await asyncio.wait_for(task, 2.0)
            except (TimeoutError, asyncio.TimeoutError, Exception):  # noqa: BLE001
                pass
        else:
            await ws.send_json(AgentEvent(kind="error", payload={
                "text": "A design run is already in progress. Pause or stop it "
                        "first."}).model_dump())
            return

    state.session["cancel"] = threading.Event()
    state.session["interrupt"] = threading.Event()
    state.session["sim_approved"] = threading.Event()

    await _broadcast(client_id, AgentEvent(kind="status", payload={
        "msg": f"case: {text[:120]}", "user_prompt": text, "mode": mode}))

    state.current_task = asyncio.create_task(_run_one_case(
        CaseMessage(text=text, mode=mode),  # type: ignore[arg-type]
        client_id=client_id, mode=mode,
        cancel_event=state.session["cancel"],
        interrupt_event=state.session["interrupt"],
        sim_approved_event=state.session["sim_approved"],
    ))


async def _on_subscriber_drop(ws: WebSocket, state: ClientState) -> None:
    """Three tiers, so a closed laptop lid does not throw away a long run but
    an abandoned session does not keep burning compute either."""
    state.subscribers.discard(ws)
    if state.subscribers:
        return
    task = state.current_task
    if task is not None and not task.done():
        if state.session["cancel"] is not None:
            state.session["cancel"].set()
        print("[app] last console closed - cancelling the in-flight run")


async def _run_one_case(
    message: CaseMessage,
    *,
    client_id: str,
    mode: str,
    cancel_event: threading.Event,
    interrupt_event: threading.Event,
    sim_approved_event: threading.Event,
) -> None:
    """Run the sync design loop in a thread and pump its events to the UI."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def emit(event: AgentEvent) -> None:
        # Called from the worker thread. This is the only thread-safety
        # contract in the system and it is the whole reason the loop can stay
        # synchronous.
        loop.call_soon_threadsafe(queue.put_nowait, event)

    use_mock_agent = _flag("MOCK_AGENT")
    mock_llm = _flag("MOCK_LLM")
    skip_db = _flag("SKIP_DB")

    def worker() -> None:
        try:
            if use_mock_agent:
                from server.app.mock_agent import run_mock_design

                run_mock_design(message, emit)
            else:
                from server.agent.agent import run_design

                run_design(message, emit, mock_llm=mock_llm, skip_db=skip_db,
                           cancel_event=cancel_event, interrupt_event=interrupt_event,
                           sim_approved_event=sim_approved_event, mode=mode,
                           client_id=client_id)
        except Exception as e:  # noqa: BLE001
            emit(AgentEvent(kind="error", payload={
                "text": f"{type(e).__name__}: {e}"}))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

    worker_task = asyncio.create_task(asyncio.to_thread(worker))
    try:
        while True:
            item = await queue.get()
            if item is _DONE:
                break
            await _broadcast(client_id, item)
    finally:
        await worker_task
        state = _clients[client_id]
        state.session["cancel"] = None
        state.session["interrupt"] = None
        state.session["sim_approved"] = None


def main() -> int:
    import uvicorn

    uvicorn.run(app, host=settings.app_host, port=settings.app_port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
