"""
FastAPI REST + WebSocket backend for the OnboardAI standalone frontend.

Run: uvicorn onboardai.api:app --port 8080 --reload
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from onboardai.graph import OnboardingEngine
from onboardai.ui.dashboard import build_dashboard_props


class _TrackedEngine(OnboardingEngine):
    """Wraps OnboardingEngine to capture the raw AgentResult from every dispatch."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_agent_transcript: str | None = None
        self.last_agent_success: bool | None = None
        self.last_failure_reason: str | None = None

    def computer_use_dispatch_node(self, state, *args, **kwargs):
        result = super().computer_use_dispatch_node(state, *args, **kwargs)
        self.last_agent_transcript = getattr(result, "raw_transcript", None) or None
        self.last_agent_success = getattr(result, "success", None)
        self.last_failure_reason = getattr(result, "failure_reason", None) or None
        return result

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="OnboardAI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev
        "http://localhost:4173",  # Vite preview
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Session store
# ---------------------------------------------------------------------------


class SessionEntry:
    def __init__(self, engine: OnboardingEngine, employee_name: str, role: str):
        self.engine = engine
        self.state = engine.new_state()
        self.messages: list[dict[str, str]] = []
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.employee_name = employee_name
        self.role = role
        self.ws_clients: list[WebSocket] = []

    def dashboard(self) -> dict[str, Any]:
        return build_dashboard_props(self.state)

    async def broadcast(self) -> None:
        if not self.ws_clients:
            return
        payload = json.dumps(self.dashboard())
        dead: list[WebSocket] = []
        for ws in self.ws_clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.ws_clients.remove(ws)


_sessions: dict[str, SessionEntry] = {}

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    employee_name: str
    role: str
    email: str | None = None


class MessageRequest(BaseModel):
    content: str


class ActionRequest(BaseModel):
    action: str  # watch_agent | self_complete | skip
    task_id: str | None = None


class TerminalRequest(BaseModel):
    command: str


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


@app.get("/api/admin/members")
async def list_members() -> list[dict]:
    rows = []
    for sid, entry in _sessions.items():
        props = entry.dashboard()
        completed = props.get("completedTasks", 0)
        total = props.get("totalTasks", 1)
        pct = round(completed / max(total, 1) * 100)
        health = entry.state.dashboard_state.health or {}
        rows.append(
            {
                "session_id": sid,
                "employee_name": entry.employee_name,
                "role": entry.role,
                "created_at": entry.created_at,
                "completed_tasks": completed,
                "total_tasks": total,
                "progress_pct": pct,
                "current_task": props.get("currentTask"),
                "current_phase": props.get("currentTaskPhase"),
                "phase_counts": props.get("phaseCounts", {}),
                "integration_health": {
                    "slack": health.get("slack", "unknown"),
                    "github": health.get("github", "unknown"),
                    "jira": health.get("jira", "unknown"),
                },
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@app.post("/api/sessions", status_code=201)
async def create_session(req: CreateSessionRequest) -> dict:
    sid = str(uuid.uuid4())
    try:
        engine = _TrackedEngine()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Engine init failed: {exc}") from exc

    entry = SessionEntry(engine, req.employee_name, req.role)

    # Kick off intake with an intro message so persona matching fires immediately
    intro = f"Hi, I'm {req.employee_name}, joining as {req.role}."
    if req.email:
        intro += f" My email is {req.email}."
    try:
        reply = await asyncio.to_thread(engine.handle_message, entry.state, intro)
        entry.messages.append({"role": "user", "content": intro})
        entry.messages.append({"role": "assistant", "content": reply})
    except Exception:
        pass  # non-fatal; session still created

    _sessions[sid] = entry
    return {"session_id": sid, "employee_name": req.employee_name}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    entry = _require(session_id)
    props = entry.dashboard()
    props["messages"] = entry.messages
    return props


@app.post("/api/sessions/{session_id}/message")
async def send_message(session_id: str, req: MessageRequest) -> dict:
    entry = _require(session_id)
    entry.messages.append({"role": "user", "content": req.content})
    try:
        reply = await asyncio.to_thread(entry.engine.handle_message, entry.state, req.content)
    except Exception as exc:
        reply = f"[Error processing message: {exc}]"
    entry.messages.append({"role": "assistant", "content": reply})
    await entry.broadcast()
    return {"reply": reply, "messages": entry.messages}


@app.post("/api/sessions/{session_id}/action")
async def session_action(session_id: str, req: ActionRequest) -> dict:
    entry = _require(session_id)
    action = req.action.lower()
    executed_task_id = entry.state.current_task_id

    if action == "watch_agent":
        msg = "run agent for me"
    elif action == "self_complete":
        msg = "mark done"
    elif action == "skip":
        msg = "skip this task"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action!r}")

    # Reset last agent transcript before running
    entry.engine.last_agent_transcript = None
    entry.engine.last_failure_reason = None

    try:
        reply = await asyncio.to_thread(entry.engine.handle_message, entry.state, msg)
    except Exception as exc:
        reply = f"[Action error: {exc}]"

    # Capture transcript — prefer raw from agent, fallback to dashboard latestTranscript
    agent_transcript = entry.engine.last_agent_transcript
    failure_reason = entry.engine.last_failure_reason

    # If blocked, build a synthetic terminal output from the failure reason
    if action == "watch_agent" and not agent_transcript and failure_reason:
        agent_transcript = f"$ (agent command)\n[exit] {failure_reason}"

    entry.messages.append({"role": "user", "content": f"[action: {action}]"})
    entry.messages.append({"role": "assistant", "content": reply})
    await entry.broadcast()
    return {
        "reply": reply,
        "dashboard": entry.dashboard(),
        "agentTranscript": agent_transcript,
        "agentSuccess": entry.engine.last_agent_success,
        "executedTaskId": executed_task_id,
    }


@app.post("/api/sessions/{session_id}/terminal")
async def run_terminal(session_id: str, req: TerminalRequest) -> dict:
    entry = _require(session_id)
    try:
        output = await asyncio.to_thread(
            entry.engine.sandbox_manager.run_command,
            entry.state.sandbox_session,
            req.command,
        )
        returncode = entry.state.sandbox_session.metadata.get("last_returncode", 0)
    except Exception as exc:
        output = f"[Error: {exc}]"
        returncode = 1
    return {"command": req.command, "output": output, "returncode": returncode}


@app.get("/api/sessions/{session_id}/checklist")
async def get_checklist(session_id: str) -> dict:
    entry = _require(session_id)
    tasks = [
        {
            "task_id": t.task_id,
            "title": t.title,
            "category": t.category,
            "phase": t.display_phase.value if t.display_phase else None,
            "status": t.status.value if t.status else None,
            "automation_mode": t.automation_mode.value if t.automation_mode else None,
            "priority": t.priority.value if t.priority else None,
            "evidence_required": t.evidence_required,
            "milestone_tag": t.milestone_tag,
        }
        for t in entry.state.task_plan
    ]
    return {"tasks": tasks, "total": len(tasks)}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


@app.websocket("/ws/{session_id}")
async def ws_endpoint(websocket: WebSocket, session_id: str) -> None:
    entry = _sessions.get(session_id)
    if entry is None:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    entry.ws_clients.append(websocket)

    # Send current state immediately on connect
    try:
        await websocket.send_text(json.dumps(entry.dashboard()))
    except Exception:
        pass

    try:
        while True:
            # Keep-alive: client can send pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in entry.ws_clients:
            entry.ws_clients.remove(websocket)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require(session_id: str) -> SessionEntry:
    entry = _sessions.get(session_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return entry
