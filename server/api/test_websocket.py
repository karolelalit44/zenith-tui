from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import uuid
from pathlib import Path
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from server.config.constants import (
    BUILD_MODE,
    TEST_SIMULATION_DIR,
    TEST_SIMULATION_DIR_ENV,
    COMPACTION_SIM_TOTAL_TOKENS,
    COMPACTION_SIM_USED_TOKENS,
    COMPACTION_SIM_AFTER_TOKENS,
    COMPACTION_SIM_SUMMARY_CHARS,
    DEFAULT_CONTEXT_WINDOW,
    MAX_EVENT_OUTPUT,
)
from server.domain.domain import ScenarioMode, SessionState
from server.domain.events import EventKind
from server.domain.message import Message, ToolCall
from server.domain.session import Session
from server.providers import responder as r
from server.toolkit import create_default_registry
from server.toolkit.executor import build_tool_metadata, execute_tool, format_tool_result
from server.toolkit.registry import ToolRegistry

from .protocol import JsonRpcRequest, make_error_response, make_response, serialize_event

logger = logging.getLogger(__name__)

_WS_TOKEN = os.environ.get("ZENITH_WS_TOKEN", "")

_MEMORY_SIM_ENTRIES = [
    {
        "id": "mem_proj_0001",
        "scope": "project",
        "title": "Backend stack choices",
        "content": "The server is FastAPI + SQLAlchemy with pydantic v2. The TUI is Ink + React on TypeScript. Both live in this monorepo; pytest covers the server and vitest covers the TUI.",
        "source": "PROJECT.md",
        "tags": ["stack", "architecture"],
        "pinned": True,
        "created_at": "2026-07-01T09:00:00Z",
        "updated_at": "2026-07-28T14:22:00Z",
        "size_chars": 196,
        "sessions": 6,
    },
    {
        "id": "mem_proj_0002",
        "scope": "project",
        "title": "WebSocket protocol notes",
        "content": "All RPC calls use JSON-RPC 2.0. Requests carry `jsonrpc`, `id`, `method` and optional `params`; events are `method: \"event\"` notifications with `kind` and `data`. The test route lives at /ws/test and mirrors the real /ws surface.",
        "source": "PROJECT.md",
        "tags": ["protocol", "transport"],
        "pinned": True,
        "created_at": "2026-07-03T11:30:00Z",
        "updated_at": "2026-07-30T10:05:00Z",
        "size_chars": 247,
        "sessions": 11,
    },
    {
        "id": "mem_proj_0003",
        "scope": "project",
        "title": "Testing conventions",
        "content": "Server tests never hit the network. TUI tests are pure-logic vitest suites against exported helpers. Keep fixtures next to their consumers.",
        "source": "PROJECT.md",
        "tags": ["tests", "conventions"],
        "pinned": False,
        "created_at": "2026-07-05T16:45:00Z",
        "updated_at": "2026-07-05T16:45:00Z",
        "size_chars": 122,
        "sessions": 4,
    },
    {
        "id": "mem_proj_0004",
        "scope": "project",
        "title": "Deployment target",
        "content": "Ship as a single Go binary once the Python server is stabilized. CI signs releases for macOS arm64, Linux x86_64, and Windows amd64.",
        "source": "PROJECT.md",
        "tags": ["deployment"],
        "pinned": False,
        "created_at": "2026-07-12T08:20:00Z",
        "updated_at": "2026-07-12T08:20:00Z",
        "size_chars": 131,
        "sessions": 2,
    },
    {
        "id": "mem_proj_0005",
        "scope": "project",
        "title": "Theme token naming",
        "content": "Theme colors are grouped as bg / border / text / status / diff / code. Never hardcode a hex color in a component; always pull from ThemeContext so custom themes keep working.",
        "source": "PROJECT.md",
        "tags": ["ui", "theme"],
        "pinned": False,
        "created_at": "2026-07-18T13:10:00Z",
        "updated_at": "2026-07-18T13:10:00Z",
        "size_chars": 184,
        "sessions": 3,
    },
    {
        "id": "mem_sess_0001",
        "scope": "session",
        "title": "Compaction fixture agreement",
        "content": "In the /compact session we agreed the canonical compaction output lives in `tui/src/fixtures/compaction-output.json` and that rawEventMapper is the single mapper shared by the live WebSocket and fixture playback.",
        "source": "f3b2c9a1-7e1d-4c2a-9f7e-2a6b3c8d9e01.md",
        "tags": ["compaction"],
        "pinned": True,
        "created_at": "2026-08-10T09:40:00Z",
        "updated_at": "2026-08-10T09:40:00Z",
        "size_chars": 217,
        "sessions": 1,
    },
    {
        "id": "mem_sess_0002",
        "scope": "session",
        "title": "Overlay routing decision",
        "content": "We decided every slash-command menu that opens a modal goes through OverlayType + OverlayRouter instead of bespoke state. New overlays must register a case in OverlayRouter and a CommandRegistry entry.",
        "source": "a7c1d3e5-8f2a-4b9e-9c4d-1b5e6f7a8b90.md",
        "tags": ["architecture", "ui"],
        "pinned": False,
        "created_at": "2026-08-11T15:15:00Z",
        "updated_at": "2026-08-11T15:15:00Z",
        "size_chars": 208,
        "sessions": 1,
    },
    {
        "id": "mem_sess_0003",
        "scope": "session",
        "title": "Prefers plans written to disk",
        "content": "The user likes every plan mode result written to PLAN.md before asking for a next step. Always offer to persist the plan instead of summarizing it inline.",
        "source": "e5d2b8f0-1c3a-4e7d-8b2f-9a4c5d6e7f80.md",
        "tags": ["preference"],
        "pinned": True,
        "created_at": "2026-08-12T10:02:00Z",
        "updated_at": "2026-08-12T10:02:00Z",
        "size_chars": 151,
        "sessions": 1,
    },
    {
        "id": "mem_sess_0004",
        "scope": "session",
        "title": "Bash tool follows OS syntax",
        "content": "On Windows the bash tool only accepts PowerShell syntax; on Unix it only accepts POSIX. This repo's tests exercise both paths, so keep Windows examples in docs and never suggest `ls`, `rm`, or `touch`.",
        "source": "c9f4e1a2-3d5b-4c8e-8f6a-1e2f3a4b5c6d.md",
        "tags": ["bash", "windows"],
        "pinned": False,
        "created_at": "2026-08-12T11:47:00Z",
        "updated_at": "2026-08-12T11:47:00Z",
        "size_chars": 236,
        "sessions": 1,
    },
]


def simulation_dir() -> Path:
    return Path(os.environ.get(TEST_SIMULATION_DIR_ENV, TEST_SIMULATION_DIR))


class TestSimulationHandler:

    def __init__(self, workspace_root: str | None = None) -> None:
        self.tool_registry: ToolRegistry = create_default_registry(
            timeout=30, provider=None, permission_service=None
        )
        self.workspace_root = workspace_root or str(Path.cwd())
        self._sessions: dict[str, Session] = {}
        self._messages: dict[str, list[Message]] = {}
        self._counters: dict[str, dict[str, int]] = {}
        self._active_tasks: dict[str, asyncio.Task] = {}


    async def handle(self, websocket: WebSocket) -> None:
        session_id = None
        ping_task = None
        try:

            async def _keepalive_ping():
                while True:
                    await asyncio.sleep(15)
                    try:
                        await websocket.send_text('{"jsonrpc":"2.0","method":"ping","params":{}}')
                    except Exception:
                        break

            ping_task = asyncio.ensure_future(_keepalive_ping())
            while True:
                raw = await websocket.receive_text()
                try:
                    data = json.loads(raw)
                    request = JsonRpcRequest(**data)
                    session_id = await self._dispatch(
                        websocket, request.method, request.id, request.params, session_id
                    )
                except json.JSONDecodeError as e:
                    await websocket.send_text(make_error_response(0, -32700, f"Parse error: {e}"))
                except Exception as e:
                    logger.exception("Test handler error")
                    await websocket.send_text(make_error_response(0, -32603, str(e)))
        except WebSocketDisconnect:
            pass
        finally:
            if ping_task:
                ping_task.cancel()
            if session_id:
                task = self._active_tasks.pop(session_id, None)
                if task:
                    task.cancel()


    async def _dispatch(
        self, ws: WebSocket, method: str, rid, params: dict, session_id: str | None
    ) -> str | None:
        handlers = {
            "session.create": lambda: self._session_create(ws, rid, params),
            "session.list": lambda: self._session_list(ws, rid, params),
            "session.list_all": lambda: self._session_list_all(ws, rid, params),
            "session.summaries": lambda: self._session_summaries(ws, rid, params),
            "session.resume": lambda: self._session_resume(ws, rid, params),
            "session.update": lambda: self._session_update(ws, rid, params, session_id),
            "session.pause": lambda: self._session_pause(ws, rid, session_id),
            "session.archive": lambda: self._session_archive(ws, rid, session_id),
            "session.delete": lambda: self._session_delete(ws, rid, params),
            "session.checkpoint": lambda: self._session_checkpoint(ws, rid, session_id),
            "session.duplicate": lambda: self._session_duplicate(ws, rid, params),
            "session.restore": lambda: self._session_restore(ws, rid, params),
            "session.export": lambda: self._session_export(ws, rid, params, session_id),
            "session.sync": lambda: self._session_sync(ws, rid, params, session_id),
            "prompt.send": lambda: self._prompt(ws, rid, params, session_id),
            "prompt.continue": lambda: self._prompt_continue(ws, rid, params, session_id),
            "prompt.cancel": lambda: self._prompt_cancel(ws, rid, params, session_id),
            "context.compact": lambda: self._context_compact(ws, rid, session_id),
            "context.clear_tools": lambda: self._context_clear_tools(ws, rid, session_id),
            "memory.list": lambda: self._memory_list(ws, rid),
            "provider.validate": lambda: self._provider_validate(ws, rid),
            "provider.models": lambda: self._provider_models(ws, rid),
            "tools.list": lambda: self._tools_list(ws, rid, params),
            "workspace.status": lambda: self._workspace_status(ws, rid, session_id),
            "workspace.diff": lambda: self._workspace_diff(ws, rid, params),
            "workspace.log": lambda: self._workspace_log(ws, rid, params),
            "workspace.repo_map": lambda: self._workspace_repo_map(ws, rid),
            "health": lambda: self._health(ws, rid),
        }
        handler = handlers.get(method)
        if handler:
            try:
                result = await handler()
                return result if isinstance(result, str) else session_id
            except Exception as e:
                logger.exception("Test handler error for method '%s'", method)
                if rid is not None:
                    await ws.send_text(
                        make_error_response(
                            rid, -32603, f"Internal error executing {method}: {e!s}"
                        )
                    )
                return session_id
        await ws.send_text(make_error_response(rid, -32601, f"Method not found: {method}"))
        return session_id


    def _get_session(self, session_id: str | None) -> Session | None:
        if not session_id:
            return None
        return self._sessions.get(session_id)

    def _make_session(self, params: dict) -> Session:
        session = Session(
            id=str(uuid.uuid4()),
            title=params.get("title", "New Session"),
            mode=params.get("mode", ScenarioMode.BUILD),
            workspace_root=params.get("workspace_root") or self.workspace_root,
            provider=params.get("provider") or "simulated",
            model=params.get("model") or "simulated-model",
        )
        session.transition(SessionState.ACTIVE)
        self._sessions[session.id] = session
        self._messages[session.id] = []
        self._counters[session.id] = {}
        return session

    async def _session_create(self, ws, rid, params) -> str:
        session = self._make_session(params)
        await self._send(
            ws,
            r.event(
                EventKind.SESSION_CREATED,
                {"session_id": session.id, "title": session.title},
                session.id,
            ),
        )
        await ws.send_text(make_response(rid, session.model_dump(mode="json")))
        return session.id

    async def _session_list(self, ws, rid, params) -> None:
        summaries = [s.to_summary_dict() for s in self._sessions.values()]
        await ws.send_text(make_response(rid, summaries))

    async def _session_list_all(self, ws, rid, params) -> None:
        include_archived = params.get("include_archived", False)
        sessions = list(self._sessions.values())
        if not include_archived:
            sessions = [s for s in sessions if s.is_active]
        if params.get("search"):
            needle = str(params["search"]).lower()
            sessions = [s for s in sessions if needle in s.title.lower()]
        limit = int(params.get("limit", 50))
        offset = int(params.get("offset", 0))
        await ws.send_text(
            make_response(rid, [s.to_summary_dict() for s in sessions[offset : offset + limit]])
        )

    async def _session_summaries(self, ws, rid, params) -> None:
        include_archived = params.get("include_archived", False)
        sessions = [s for s in self._sessions.values() if include_archived or s.is_active]
        limit = int(params.get("limit", 10))
        await ws.send_text(make_response(rid, [s.to_summary_dict() for s in sessions[:limit]]))

    async def _session_resume(self, ws, rid, params) -> str | None:
        sid = params.get("session_id", "")
        session = self._sessions.get(sid)
        if not session:
            await ws.send_text(make_error_response(rid, -32602, f"Session not found: {sid}"))
            return None
        session.state = SessionState.ACTIVE
        messages = [m.model_dump(mode="json") for m in self._messages.get(sid, [])]
        await ws.send_text(
            make_response(
                rid,
                {
                    "session": session.model_dump(mode="json"),
                    "messages": messages,
                    "events_replayed": 0,
                    "sync_events": [],
                    "latest_sequence": len(messages),
                },
            )
        )
        return sid

    async def _session_update(self, ws, rid, params, session_id) -> None:
        sid = params.get("session_id", session_id)
        session = self._sessions.get(sid)
        if not session:
            await ws.send_text(make_error_response(rid, -32602, f"Session not found: {sid}"))
            return
        if params.get("title"):
            session.title = params["title"]
        session.updated_at = params.get("updated_at") or session.updated_at
        await ws.send_text(make_response(rid, {"session": session.model_dump(mode="json")}))

    async def _session_pause(self, ws, rid, session_id) -> None:
        session = self._get_session(session_id)
        if not session:
            await ws.send_text(make_error_response(rid, -32602, "No active session"))
            return
        session.transition(SessionState.PAUSED)
        await self._send(
            ws, r.event(EventKind.SESSION_PAUSED, {"session_id": session.id}, session.id)
        )
        await ws.send_text(make_response(rid, {"session_id": session.id, "status": "paused"}))

    async def _session_archive(self, ws, rid, session_id) -> None:
        session = self._get_session(session_id)
        if not session:
            await ws.send_text(make_error_response(rid, -32602, "No active session"))
            return
        session.archive()
        await ws.send_text(make_response(rid, {"session_id": session.id, "status": "archived"}))

    async def _session_delete(self, ws, rid, params) -> None:
        sid = params.get("session_id", "")
        if sid in self._sessions:
            del self._sessions[sid]
            self._messages.pop(sid, None)
            self._counters.pop(sid, None)
        await ws.send_text(make_response(rid, {"session_id": sid, "status": "deleted"}))

    async def _session_checkpoint(self, ws, rid, session_id) -> None:
        session = self._get_session(session_id)
        if not session:
            await ws.send_text(make_error_response(rid, -32602, "No active session"))
            return
        await self._send(
            ws,
            r.event(EventKind.SESSION_CHECKPOINT_CREATED, {"session_id": session.id}, session.id),
        )
        await ws.send_text(
            make_response(
                rid,
                {
                    "session_id": session.id,
                    "checkpoint_id": f"chk_{session.id[:8]}",
                    "status": "checkpointed",
                },
            )
        )

    async def _session_duplicate(self, ws, rid, params) -> None:
        sid = params.get("session_id", "")
        source = self._sessions.get(sid)
        if not source:
            await ws.send_text(make_error_response(rid, -32602, f"Session not found: {sid}"))
            return
        new_session = source.model_copy(deep=True)
        new_session.id = str(uuid.uuid4())
        new_session.title = f"{source.title} (copy)"
        new_session.parent_session_id = source.id
        new_session.state = SessionState.CREATED
        self._sessions[new_session.id] = new_session
        self._messages[new_session.id] = [
            m.model_copy(deep=True) for m in self._messages.get(sid, [])
        ]
        self._counters[new_session.id] = {}
        await ws.send_text(
            make_response(rid, {"session": new_session.model_dump(mode="json"), "original_id": sid})
        )

    async def _session_export(self, ws, rid, params, session_id) -> None:
        params.get("session_id", session_id)
        await ws.send_text(
            make_response(
                rid,
                {
                    "markdown": "",
                    "note": "Export is unavailable on the /ws/test backend (no database).",
                },
            )
        )

    async def _session_restore(self, ws, rid, params) -> None:
        sid = params.get("session_id", "")
        session = self._sessions.get(sid)
        if not session:
            await ws.send_text(make_error_response(rid, -32602, f"Session not found: {sid}"))
            return
        session.state = SessionState.ACTIVE
        session.is_active = True
        await ws.send_text(make_response(rid, session.model_dump(mode="json")))

    async def _session_sync(self, ws, rid, params, session_id) -> None:
        sid = params.get("session_id", session_id)
        if not sid:
            await ws.send_text(make_error_response(rid, -32602, "No session_id provided"))
            return
        await ws.send_text(
            make_response(
                rid,
                {
                    "events": [],
                    "latest_sequence": len(self._messages.get(sid, [])),
                },
            )
        )


    async def _ensure_session(self, ws, rid, params, session_id, content: str) -> str | None:
        if session_id and session_id in self._sessions:
            return session_id
        if not content.strip():
            await ws.send_text(make_error_response(rid, -32602, "Empty prompt"))
            return None
        return self._make_session(
            {
                "title": content[:50],
                "mode": params.get("mode"),
                "workspace_root": params.get("workspace_root"),
            }
        ).id

    async def _prompt(self, ws, rid, params, session_id) -> str | None:
        content = params.get("content", "") or params.get("prompt", "")
        if not content.strip():
            await ws.send_text(make_error_response(rid, -32602, "Empty prompt"))
            return session_id
        session_id = params.get("session_id") or session_id
        session_id = await self._ensure_session(ws, rid, params, session_id, content)
        if session_id is None:
            return None
        session = self._sessions[session_id]
        self._apply_mode(session, params)
        user_msg = Message(session_id=session_id, role="user", content=content)
        self._messages.setdefault(session_id, []).append(user_msg)
        await ws.send_text(make_response(rid, {"session_id": session_id, "status": "processing"}))
        self._run_playback(ws, session, content)
        return session_id

    async def _prompt_continue(self, ws, rid, params, session_id) -> str | None:
        session_id = params.get("session_id") or session_id
        if not session_id or session_id not in self._sessions:
            await ws.send_text(make_error_response(rid, -32602, "No active session"))
            return session_id
        content = params.get("content", "") or "continue"
        session = self._sessions[session_id]
        self._apply_mode(session, params)
        await ws.send_text(make_response(rid, {"session_id": session_id, "status": "processing"}))
        self._run_playback(ws, session, content)
        return session_id

    def _apply_mode(self, session: Session, params: dict) -> None:
        raw = params.get("mode")
        if not raw:
            return
        try:
            session.mode = ScenarioMode(str(raw).strip().lower())
        except ValueError:
            logger.warning("Invalid mode '%s' ignored", raw)

    async def _prompt_cancel(self, ws, rid, params, session_id) -> None:
        sid = params.get("session_id") or session_id
        if sid and sid in self._sessions:
            task = self._active_tasks.pop(sid, None)
            if task:
                task.cancel()
            await self._send(
                ws,
                r.event(
                    EventKind.ERROR,
                    {"message": "Prompt cancelled", "code": "cancelled", "recoverable": True},
                    sid,
                ),
            )
        await ws.send_text(make_response(rid, {"cancelled": True}))


    def _run_playback(self, ws: WebSocket, session: Session, content: str) -> None:
        prev = self._active_tasks.get(session.id)
        if prev:
            prev.cancel()
        task = asyncio.ensure_future(self._playback(ws, session, content))
        self._active_tasks[session.id] = task

    def _load_simulations(self) -> list[dict[str, Any]]:
        root = simulation_dir()
        files = []
        try:
            if not root.is_dir():
                logger.warning("Simulation dir does not exist: %s", root)
                return []
            for path in sorted(root.glob("*.json")):
                try:
                    with path.open("r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    if isinstance(data, dict):
                        data["_file"] = path.name
                        files.append(data)
                except (OSError, json.JSONDecodeError) as e:
                    logger.warning("Skipping invalid simulation file %s: %s", path, e)
        except OSError as e:
            logger.warning("Failed to scan simulation dir: %s", e)
        return files

    def _match(self, simulations: list[dict], content: str, mode: str) -> dict | None:
        text = content.strip().lower()
        for sim in simulations:
            if sim.get("_file", "").startswith("_"):
                continue
            rules = sim.get("match") or {}
            if not self._rules_match(rules, text, mode):
                continue
            return sim
        for sim in simulations:
            if sim.get("_file", "").startswith("_"):
                return sim
        return None

    def _rules_match(self, rules: dict, text: str, mode: str) -> bool:
        exact = (rules.get("exact") or "").strip().lower()
        contains = (rules.get("contains") or "").strip().lower()
        rule_mode = (rules.get("mode") or "").strip().lower()
        if rule_mode and rule_mode != mode:
            return False
        if exact and text != exact:
            return False
        return not (contains and contains not in text)

    def _pick_response(self, session: Session, sim: dict) -> dict:
        responses = sim.get("responses") or []
        if not responses:
            return {}
        mode = sim.get("mode", "round_robin")
        key = sim.get("_file", sim.get("name", "unknown"))
        counter = self._counters.setdefault(session.id, {})
        index = counter.get(key, 0)
        if mode == "random":
            entry = random.choice(responses)
        else:
            entry = responses[index % len(responses)]
            counter[key] = index + 1
        return entry

    async def _playback(self, ws: WebSocket, session: Session, content: str) -> None:
        session.state = SessionState.ACTIVE
        simulations = self._load_simulations()
        sim = self._match(simulations, content, session.mode.value)
        if sim is None:
            sim = {
                "_file": "_default.json",
                "name": "default",
                "mode": "round_robin",
                "responses": [
                    {
                        "reasoning": "No simulation file matched this prompt.",
                        "content": (
                            "No simulation file matched this prompt. Add a file under "
                            "data/simulation/ to script a response for it."
                        ),
                        "chunk_size": 6,
                        "delay_ms": 25,
                    }
                ],
            }
        session.model = session.model or "simulated-model"
        session.provider = session.provider or "simulated"
        try:
            await self._play_turn(ws, session, sim)
            await self._send(ws, r.success("Simulated response complete", session.id, iterations=1))
            session.transition(SessionState.COMPLETED)
        except asyncio.CancelledError:
            await self._send(
                ws,
                r.error(
                    "Simulated response interrupted",
                    session.id,
                    code="cancelled",
                    recoverable=True,
                ),
            )
            raise
        except Exception as e:
            logger.exception("Playback failed for session %s", session.id)
            await self._send(ws, r.error(str(e), session.id, code="simulation_error"))

    async def _play_turn(self, ws: WebSocket, session: Session, sim: dict) -> None:
        turns = 0
        entry = self._pick_response(session, sim)
        while entry:
            turns += 1
            if turns > 12:
                logger.warning("Simulation %s exceeded turn limit", sim.get("_file"))
                break

            events = entry.get("events") or []
            if events:
                for evt in events:
                    kind = evt.get("kind", "message")
                    if kind == "thinking":
                        await self._send(ws, r.thinking(evt.get("text", ""), session.id))
                        await asyncio.sleep(0.15)
                    elif kind == "message":
                        content = evt.get("text", "")
                        await self._stream_content(ws, session, entry, content)
                    elif kind == "tool_step":
                        tool_name = evt.get("tool", "")
                        params = evt.get("params") or {}
                        output = evt.get("output", "")
                        success = evt.get("success", True)
                        await self._send(ws, r.tool_call(tool_name, params, session.id))
                        await asyncio.sleep(0.15)
                        await self._send(ws, r.tool_result(tool_name, success, session.id, output=output, error=""))
                    elif kind == "agent_orchestration":
                        evt_data = {k: v for k, v in evt.items() if k != "kind"}
                        await self._send(
                            ws,
                            r.event(
                                EventKind.AGENT_ORCHESTRATION,
                                evt_data,
                                session.id,
                            ),
                        )
                        await asyncio.sleep(0.6)
                    else:
                        evt_data = {k: v for k, v in evt.items() if k != "kind"}
                        try:
                            ek = EventKind(kind)
                        except ValueError:
                            ek = EventKind.MESSAGE
                        await self._send(
                            ws,
                            r.event(
                                ek,
                                evt_data,
                                session.id,
                            ),
                        )
                        await asyncio.sleep(0.15)

            reasoning = entry.get("reasoning")
            if reasoning and not events:
                await self._send(ws, r.thinking(reasoning, session.id))
                await asyncio.sleep(0.05)

            content = entry.get("content", "")
            if content and not events:
                await self._stream_content(ws, session, entry, content)

            tool_calls = entry.get("tool_calls") or []
            if tool_calls:
                for call in tool_calls:
                    tool_name = call.get("tool", "")
                    params = call.get("params") or {}
                    await self._execute_tool_call(ws, session, tool_name, params)

            if not tool_calls and not events:
                break

            responses = sim.get("responses") or []
            if len(responses) > turns:
                entry = self._pick_response(session, sim)
            else:
                break

    async def _stream_content(
        self, ws: WebSocket, session: Session, entry: dict, content: str
    ) -> None:
        if not content:
            return
        chunk_size = int(entry.get("chunk_size", 3) or 3)
        delay = float(entry.get("delay_ms", 25) or 25) / 1000.0
        for i in range(0, len(content), chunk_size):
            await self._send(
                ws, r.message_event(content[i : i + chunk_size], session.id, partial=True, iteration=0)
            )
            await asyncio.sleep(delay)
        await self._send(ws, r.message_event(content, session.id, partial=False, iteration=0))
        self._messages.setdefault(session.id, []).append(
            Message(session_id=session.id, role="assistant", content=content)
        )

    async def _execute_tool_call(
        self, ws: WebSocket, session: Session, tool_name: str, params: dict
    ) -> None:
        await self._send(ws, r.tool_call(tool_name, params, session.id))
        result, duration_ms = await execute_tool(
            self.tool_registry, tool_name, params, session.workspace_root, BUILD_MODE
        )
        text = format_tool_result(tool_name, result)
        await self._send(
            ws,
            r.tool_result(
                tool_name,
                result.success,
                session.id,
                output=text[:MAX_EVENT_OUTPUT],
                error=result.error,
                metadata=build_tool_metadata(
                    tool_name, params, result, duration_ms, session.workspace_root
                ),
            ),
        )
        self._messages.setdefault(session.id, []).append(
            Message(
                session_id=session.id,
                role="assistant",
                content="",
                metadata={"tool": tool_name},
                tool_calls=[ToolCall(name=tool_name, arguments=params)],
            )
        )

    async def _send(self, ws: WebSocket, event: Any) -> None:
        await ws.send_text(serialize_event(event))


    async def _context_compact(self, ws, rid, session_id) -> None:
        session = self._get_session(session_id)
        if not session:
            await ws.send_text(make_error_response(rid, -32602, "No active session"))
            return

        total = COMPACTION_SIM_TOTAL_TOKENS
        used = COMPACTION_SIM_USED_TOKENS

        await self._send(
            ws,
            r.context_compaction_started(
                session_id=session_id,
                reason="context pressure",
                used=used,
                total=total,
            ),
        )
        await asyncio.sleep(0.35)

        await self._send(
            ws,
            r.context_compaction_phase(
                session_id=session_id,
                phase="preserving",
                label="Preserving important context",
            ),
        )
        await asyncio.sleep(0.35)

        tool_steps = ["bash_output", "file_read_output", "tool_result_traces"]
        saved_per_step = 12_000 // len(tool_steps)
        for tool in tool_steps:
            await self._send(
                ws,
                r.context_compacted(
                    tool,
                    chars_removed=30_000,
                    tokens_saved=saved_per_step,
                    reason="compaction",
                    session_id=session_id,
                ),
            )
            await asyncio.sleep(0.25)

        await self._send(
            ws,
            r.context_compaction_phase(
                session_id=session_id,
                phase="compacting",
                label="Compacting context",
                before_tokens=used,
                after_tokens=COMPACTION_SIM_AFTER_TOKENS,
            ),
        )
        await asyncio.sleep(0.3)

        await self._send(
            ws,
            r.context_compaction_phase(
                session_id=session_id,
                phase="verifying",
                label="Verifying preserved context",
            ),
        )
        await asyncio.sleep(0.35)

        await self._send(
            ws,
            r.context_compaction_ended(
                session_id=session_id,
                reason="completed",
                used=COMPACTION_SIM_AFTER_TOKENS,
                total=total,
                tokens_saved=used - COMPACTION_SIM_AFTER_TOKENS,
                summary_chars=COMPACTION_SIM_SUMMARY_CHARS,
                preserved={
                    "requirements": 12,
                    "decisions": 7,
                    "openTasks": 4,
                    "findings": 3,
                    "artifacts": 3,
                    "agents": 2,
                },
                failed=False,
                summary=(
                    "## Objective\n"
                    "- Make the zenith TUI /compact turn fully data-driven: a single JSON fixture holds "
                    "the exact AI-model compaction output, a shared emitter replays it, and the same "
                    "renderer consumes it in production and in tests.\n"
                    "\n"
                    "## Important Details\n"
                    "- /compact replays `src/fixtures/compaction-output.json` locally through "
                    "`emitCompactionFixture` — no backend dependency.\n"
                    "- `mapRawEvent` lives in `src/services/transport/rawEventMapper.ts` and is shared by "
                    "the live WebSocket stream and fixture playback, so formats stay byte-for-byte identical.\n"
                    "- The lifecycle collapses into one `ContextCompactionFlowEvent`; "
                    "`context_compaction_ended` is always terminal.\n"
                    "\n"
                    "## Work State\n"
                    "### Completed\n"
                    "- JSON-driven pipeline: fixture, rawEventMapper, fixtureEmitter, useScenario switch, "
                    "App guard removal.\n"
                    "- CompactionFlowBlock redesigned as a branded card: model, runtime, token transition, "
                    "preserved metrics.\n"
                    "\n"
                    "### Active\n"
                    "- None.\n"
                    "\n"
                    "### Blocked\n"
                    "- None.\n"
                    "\n"
                    "## Next Move\n"
                    "1. Render the summary body with TerminalMarkdown so structured sections display correctly.\n"
                    "2. Mirror the structured summary in the live /ws/test simulation for parity.\n"
                    "\n"
                    "## Relevant Files\n"
                    "- `tui/src/fixtures/compaction-output.json` — canonical compaction output.\n"
                    "- `tui/src/services/transport/fixtureEmitter.ts` — shared emitter for runtime and tests.\n"
                    "- `tui/src/components/Display/Scenario/CompactionFlowBlock.tsx` — the compaction turn card.\n"
                    "- `server/api/test_websocket.py` — live compaction simulation."
                ),
            ),
        )

        await ws.send_text(make_response(rid, {"status": "compacted"}))

    async def _context_clear_tools(self, ws, rid, session_id) -> None:
        if not session_id:
            await ws.send_text(make_error_response(rid, -32602, "No active session"))
            return
        await ws.send_text(make_response(rid, {"status": "tools_cleared"}))

    async def _memory_list(self, ws, rid) -> None:
        await ws.send_text(
            make_response(
                rid,
                {"memories": _MEMORY_SIM_ENTRIES, "total": len(_MEMORY_SIM_ENTRIES)},
            )
        )

    async def _provider_validate(self, ws, rid) -> None:
        await ws.send_text(
            make_response(rid, {"provider": "simulated", "valid": True, "message": "Simulated"})
        )

    async def _provider_models(self, ws, rid) -> None:
        await ws.send_text(
            make_response(
                rid,
                {
                    "models": [
                        {
                            "id": "simulated-model",
                            "name": "Simulated Model",
                            "contextWindow": DEFAULT_CONTEXT_WINDOW,
                        }
                    ]
                },
            )
        )

    async def _tools_list(self, ws, rid, params) -> None:
        mode = params.get("mode", BUILD_MODE)
        tools = [
            {"name": name, "description": "", "schema": {}}
            for name in self.tool_registry.list_tools_for_mode(mode)
        ]
        await ws.send_text(make_response(rid, {"tools": tools}))

    async def _workspace_status(self, ws, rid, session_id) -> None:
        session = self._get_session(session_id)
        await ws.send_text(
            make_response(
                rid,
                {
                    "workspace_root": session.workspace_root if session else self.workspace_root,
                    "simulated": True,
                },
            )
        )

    async def _workspace_diff(self, ws, rid, params) -> None:
        await ws.send_text(make_response(rid, {"files": [], "simulated": True}))

    async def _workspace_log(self, ws, rid, params) -> None:
        await ws.send_text(make_response(rid, {"entries": []}))

    async def _workspace_repo_map(self, ws, rid) -> None:
        await ws.send_text(make_response(rid, {"tree": [], "simulated": True}))

    async def _health(self, ws, rid) -> None:
        await ws.send_text(make_response(rid, {"status": "ok", "backend": "simulated"}))
