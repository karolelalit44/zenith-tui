from __future__ import annotations
import asyncio
import json
import logging
import re
import time
from collections import Counter
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from server.config.constants import (
    BASH_TOOL,
    BG_OUTPUT_TAIL,
    BUILD_MODE,
    CONTEXT_EXHAUSTED_HINT,
    CONTEXT_EXHAUSTED_MESSAGE,
    DEFAULT_SALVAGE_TIMEOUT_SECONDS,
    DUP_RESULT_PREVIEW_CHARS,
    EPHEMERAL_TOOL_WINDOW_SIZE,
    EXPLORE_TOOL,
    FILE_DELETE_TOOL,
    FILE_EDIT_TOOL,
    FILE_MUTATING_TOOLS,
    FILE_OVERWRITE_PARAM,
    FILE_WRITE_TOOL,
    GET_TOOL_DEFINITION_TOOL,
    HARD_STOP_USAGE_RATIO,
    MANIFEST_CHECKS_CAP,
    APPOGEE_AGENT_NAME,
    APPOGEE_AGENT_ROLE,
    PLAN_MODE,
    POLL_TOOLS,
    PROGRESS_DETAIL_MAX_CHARS,
    SKIP_WARNING_CAP,
    SALVAGE_DIGEST_MAX_ITEMS,
    SALVAGE_INSTRUCTION,
    SALVAGE_TIMEOUT_ENV,
    STALL_FINALIZE_AFTER_ITERATIONS,
    SUMMARY_MIN_CHARS,
    TERMINAL_TOOL,
    TURN_VERDICT_COMPLETED,
    TURN_VERDICT_STALLED,
)
from server.config.env import optional_float
from server.config.settings import AGENT_MODES, AppSettings
from server.domain.enums import FinishReason
from server.domain.errors import ZenithError
from server.domain.events import Event, EventKind
from server.domain.message import Message
from server.providers import responder as r
from server.providers.base import BaseProvider
from server.providers.parser import UnifiedResponseFormatter
from server.toolkit.base import ToolResult
from server.toolkit.digest import format_tool_digest
from server.toolkit.param_normalizer import canonicalize_path_values, normalize_file_params
from server.toolkit.path_validator import validate_path
from server.toolkit.registry import ToolRegistry
from server.toolkit.resolver import SchemaResolver, build_mode_tool_seed

from ..toolkit.executor import (
    _dynamic_max_output,
    auto_commit,
    build_tool_metadata,
    execute_tool,
    format_tool_result,
    post_execution_hooks,
    validate_tool_calls,
    validate_tool_rejection,
)
from .compaction import compact_tool_output
from .compaction_service import (
    CompactionService,
    CompactionTrigger,
    compact_live_tail,
)
from .context import ContextManager, _adaptive_reserve, _get_model_context_window
from .llm_stream import StreamState, stream_completion
from .prompts import build_plan_system_prompt, build_system_prompt
from .run_state import _activity_label
from .validation import reflection_error_limit, schemas_to_openai_tools

_format_tool_result = format_tool_result
logger = logging.getLogger(__name__)


def _call_signature(
    tool_name: str, params: dict, workspace_root: str | None = None
) -> tuple[str, str]:
    canonical = canonicalize_path_values(params, workspace_root) if workspace_root else params
    return (
        tool_name,
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str),
    )


def _params_label(params: dict) -> str:
    if not params:
        return ""
    for key in ("path", "filepath", "pattern", "command", "query"):
        value = params.get(key)
        if value:
            limit = 48 if key == "command" else 120
            return f"{key}={str(value)[:limit]}"
    if len(params) == 1:
        return str(next(iter(params.values())))[:120]
    return ", ".join(f"{key}={value}" for key, value in sorted(params.items()))[:120]


def _incomplete_todo_titles(todos: list[dict] | None) -> list[str]:
    completed_statuses = {"completed", "complete", "cancelled", "canceled"}
    return [
        str(todo.get("title") or todo.get("content") or "Untitled task")
        for todo in todos or []
        if str(todo.get("status", "pending")).lower() not in completed_statuses
    ]


def _scan_plan_artifacts(workspace_root: str | None) -> dict:
    """Return the on-disk plan-artifact contract (plan.md is blocking, todo.md
    recommended) as ``plan_written`` / ``todo_written`` / ``missing``."""
    root = Path(workspace_root or ".")
    missing: list[str] = []
    plan_written = bool((root / "plan.md").is_file())
    todo_written = bool((root / "todo.md").is_file())
    if not plan_written:
        missing.append("plan.md")
    if not todo_written:
        missing.append("todo.md")
    return {
        "plan_written": plan_written,
        "todo_written": todo_written,
        "missing": missing,
    }


def _build_manifest(
    created_files: set[str],
    files_edited: list[str],
    task_completed: bool,
    stall_finalized: bool,
    last_text: str = "",
    workspace_root: str | None = None,
    verification: list[dict] | None = None,
    plan_mode: bool = False,
    todos: list[dict] | None = None,
) -> dict:
    """Evidence-derived turn manifest (QA-3/QA-8).

    ``created``/``modified`` come from executed tool success, never prose.
    ``remaining`` comes from structured state — incomplete session todos plus a
    verification-gap note when work happened — never the model's last message.
    In plan mode the manifest also carries the plan-artifact contract
    (``plan_artifacts``) and corrects ``remaining`` when plan.md was not written.
    """
    created = sorted(created_files)
    modified = sorted(p for p in files_edited if p not in created_files)
    completed = bool(task_completed and not stall_finalized)
    changed = bool(created_files or files_edited)
    verified = True if not changed else _has_verification_evidence(verification or [])
    remaining: list[str] = []
    if not completed:
        
        remaining = _incomplete_todo_titles(todos)
        if created_files and not verified:
            remaining.append("Files were written but no verification evidence was produced.")
        elif files_edited and not verified:
            remaining.append("Files were modified but no verification evidence was produced.")
    answer_text = (last_text or "").strip()
    payload: dict = {
        "created": created,
        "modified": modified,
        "remaining": remaining,
        "completed": completed,
        "stalled": bool(stall_finalized),
        "verified": verified,
        # A substantive delivered message counts as an answered turn even when
        # no files were touched.
        "answered": bool(answer_text) and len(answer_text) >= SUMMARY_MIN_CHARS,
        "verdict": TURN_VERDICT_STALLED if stall_finalized else TURN_VERDICT_COMPLETED,
        "checks": [
            {k: v for k, v in (c or {}).items() if k != "seq"} for c in (verification or [])
        ],
    }
    if plan_mode:
        artifacts = _scan_plan_artifacts(workspace_root)
        payload["plan_artifacts"] = artifacts
        # The plan.md requirement is the hard half of the contract: a plan turn
        # that did not leave plan.md on disk has remaining work regardless of the
        # model's prose. todo.md is recommended but not blocking — its absence is
        # reported in plan_artifacts.missing but does not force remaining.
        if artifacts["missing"] and "plan.md" in artifacts["missing"]:
            label = "Plan artifacts not written: " + ", ".join(artifacts["missing"]) + "."
            if label not in remaining:
                remaining.append(label)
            payload["remaining"] = remaining
    files: list[dict] = []
    if created_files:
        root = Path(workspace_root or ".")
        for p in created:
            resolved = root / p
            exists = resolved.exists()
            files.append(
                {
                    "path": p,
                    "exists": exists,
                    "size": resolved.stat().st_size if exists else 0,
                }
            )
    payload["files"] = files
    return payload


_STRIP_PAYLOAD_MIN_VALUE = 200
_WRITE_PAYLOAD_RE = re.compile(r'([\'"]content[\'"]\s*:\s*)([\'"].*?[\'"])', re.DOTALL)


def _strip_write_payload_from_assistant_messages(messages: list[dict], file_path: str) -> None:
    def _replace(match: re.Match) -> str:
        value = match.group(2)
        # Only rewrite genuine embedded payloads; short quoted values are
        # almost certainly prose discussing the file, not the file body.
        if len(value) >= _STRIP_PAYLOAD_MIN_VALUE:
            return f'{match.group(1)}"[content omitted; file written]"'
        return match.group(0)

    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if (
                isinstance(content, str)
                and file_path in content
                and len(content) > 500
                and ('"content":' in content or "'content':" in content)
            ):
                msg["content"] = _WRITE_PAYLOAD_RE.sub(_replace, content)
            break


def _all_calls_repeat(
    valid_calls: list[dict], executed: set[tuple[str, str]], workspace_root: str | None = None
) -> bool:
    if not valid_calls or not executed:
        return False
    for tc in valid_calls:
        if tc["tool"] in POLL_TOOLS:
            return False
        sig = _call_signature(
            tc["tool"],
            normalize_file_params(tc.get("params", {}), tc["tool"]),
            workspace_root,
        )
        if sig not in executed:
            return False
    return True


def _most_common_count(items: list[str]) -> int:
    """Most-frequent item count (kept for diagnostics tooling)."""
    if not items:
        return 0
    return Counter(items).most_common(1)[0][1]


def _is_degenerate_message(text: str | None) -> bool:
    """True for meta-placeholder outputs (P3.3): ``[tool calls]``, ``thinking``.

    Weak models occasionally emit these instead of content. They must never be
    rendered to the user as an assistant answer. Blank/whitespace-only text
    also counts: there is nothing to render.
    """
    if not text:
        return True
    stripped = text.strip()
    if not stripped:
        return True
    normalized = stripped.lower()
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1].strip()
    normalized = " ".join(normalized.split())
    if normalized in {"thinking", "no output"}:
        return True
    return normalized.replace(" ", "") in {"toolcall", "toolcalls"}


def _has_tool_calls(tool_calls: list[dict]) -> bool:
    """Check whether the model produced any tool calls."""
    return bool(tool_calls)


def _has_verification_evidence(checks: list[dict], after_seq: int | None = None) -> bool:
    for check in checks or []:
        if (check.get("output_len") or 0) > 0 and (
            after_seq is None or (check.get("seq") or 0) >= after_seq
        ):
            return True
    return False


def _pending_background_completions() -> list:
    try:
        from server.toolkit.tools.background import get_background_manager

        return get_background_manager().pending_completions()
    except Exception:
        return []


class AgentLoop:
    def __init__(
        self,
        config: AppSettings,
        provider: BaseProvider,
        context_manager: ContextManager | None = None,
        tool_registry: ToolRegistry | None = None,
        compaction_service: CompactionService | None = None,
    ) -> None:
        self.config = config
        self.provider = provider
        self.context_manager = context_manager or ContextManager(config)
        self.tool_registry = tool_registry
        self._compaction_service = compaction_service
        self._summary: str | None = None
        self._accept_sequence: int = 0
        self._cancel_sequence: int = -1
        self._last_emitted_message: str | None = None
        self._compacted_this_turn = False
        self._compacted_message_count = 0
        self._last_compaction_outcome = None
        self._heavy_tools_summarized = 0
        self._heavy_seq = 0
        
        self._salvage_instruction: str = SALVAGE_INSTRUCTION

    def _get_compaction_service(self) -> CompactionService:
        if self._compaction_service is None:
            self._compaction_service = CompactionService(
                self.config, self.provider, self.context_manager
            )
        return self._compaction_service

    async def _maybe_summarize_heavy_output(
        self, session_id: str, tool_name: str, result: ToolResult
    ) -> str | None:
        return None

    @staticmethod
    def _salvage_digest(messages: list[dict]) -> str:
        """Deterministic fallback answer built from the turn's tool digests.

        Used only when the salvage completion fails outright or the model
        tries to keep calling tools. Guarantees the turn still ends with a
        truthful, non-empty account of what happened.
        """
        digs = [str(m.get("digest")) for m in messages if isinstance(m, dict) and m.get("digest")]
        if not digs:
            return ""
        shown = digs[-SALVAGE_DIGEST_MAX_ITEMS:]
        omitted = len(digs) - len(shown)
        lines = [
            "The turn ended before a final answer could be produced. Tool activity this turn:",
        ]
        lines.extend(f"- {d}" for d in shown)
        if omitted > 0:
            lines.append(f"(+{omitted} earlier steps omitted)")
        return "\n".join(lines)

    async def _salvage_final_answer(
        self,
        *,
        session_id: str,
        messages: list[dict],
        model: str,
        reason: str,
        iteration: int,
    ) -> AsyncIterator[Event]:

        
        yield r.warning(
            f"Wrapping up without further tool use ({reason})...",
            session_id,
            code="SALVAGE",
        )
        payload = list(messages) + [{"role": "user", "content": self._salvage_instruction}]
        text = ""
        try:
            result = await asyncio.wait_for(
                self.provider.complete(payload),
                timeout=optional_float(SALVAGE_TIMEOUT_ENV, DEFAULT_SALVAGE_TIMEOUT_SECONDS),
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Salvage completion failed (%s); using deterministic digest", e)
        else:
            raw = (result or "").strip()
            clean, attempted_calls = UnifiedResponseFormatter.process_response(raw)
            if attempted_calls:
                logger.info(
                    "Salvage reply contained %d tool call(s); discarding.", len(attempted_calls)
                )
            text = "" if _is_degenerate_message(clean) else clean.strip()
        if not text:
            text = self._salvage_digest(messages)
        if not text:
            return
        logger.info(
            "SALVAGE: reason=%s iteration=%d produced %d chars", reason, iteration, len(text)
        )
        yield r.message_event(text, session_id, partial=False, iteration=max(1, iteration))
        self._last_emitted_message = text

    def accept(self) -> int:
        self._accept_sequence += 1
        return self._accept_sequence

    @staticmethod
    def _explore_crewmate_identity(tool_params: dict) -> tuple[str, str, str]:
        """(name, role, task) for an explore call's crewmate card."""
        custom = (
            tool_params.get("crewmate") if isinstance(tool_params.get("crewmate"), dict) else {}
        )
        name = str(custom.get("name") or "").strip() or APPOGEE_AGENT_NAME
        role = str(custom.get("role") or "").strip() or APPOGEE_AGENT_ROLE
        task = str(tool_params.get("objective") or "").strip()
        return name[:48], role[:48], task[:200]

    def _explore_spawn_event(self, session_id: str, tool_params: dict) -> Event | None:
        import uuid

        name, role, task = self._explore_crewmate_identity(tool_params)
        return Event(
            kind=EventKind.CREWMATE_SPAWNED,
            data={
                "crewmate_id": EXPLORE_TOOL,
                "name": name,
                "role": role,
                "task_id": str(uuid.uuid4())[:8],
                "capability": "explore_delegation",
                "parent_session_id": session_id,
                "task": task,
                "status": "working",
            },
            session_id=session_id,
        )

    @staticmethod
    def _explore_settle_event(session_id: str, spawn_data: dict, result: ToolResult) -> Event:
        meta = result.metadata or {}
        summary = str(
            meta.get("summary")
            or meta.get("explore_status")
            or ("Mission complete" if result.success else result.error or "Mission failed")
        )
        ok = bool(result.success)
        return Event(
            kind=EventKind.CREWMATE_COMPLETE if ok else EventKind.CREWMATE_FAILED,
            data={
                "crewmate_id": spawn_data.get("crewmate_id") or EXPLORE_TOOL,
                "task_id": spawn_data.get("task_id") or "",
                "result_summary": summary[:200],
                "status": str(meta.get("explore_status") or ("completed" if ok else "failed")),
                "tokens_used": meta.get("tokens_used"),
                "duration_ms": meta.get("duration_ms"),
                **({"error": result.error} if (not ok and result.error) else {}),
            },
            session_id=session_id,
        )

    def cancel(self) -> None:
        self._cancel_sequence = self._accept_sequence

    def is_cancelled(self, sequence: int) -> bool:
        return self._cancel_sequence >= sequence

    @property
    def summary(self) -> str | None:
        return self._summary

    def set_summary(self, summary: str | None) -> None:
        self._summary = summary

    def _resolve_safety_iterations(self, model: str) -> int:
        ctx = _get_model_context_window(model)
        return max(10, min(ctx // 2000, 150))

    def _mode_tools_budget(self, model: str, mode: str) -> int:
        """Cap on-band tool schemas to a fixed share of usable input context."""
        ctx = min(_get_model_context_window(model), self.config.max_context_tokens)
        reserve = _adaptive_reserve(model, ctx)
        return int(max(0, ctx - reserve) * 0.10)

    async def process_prompt(
        self,
        prompt: str,
        session_id: str,
        history: list[Message],
        mode: str = BUILD_MODE,
        plan_context: str = "",
        model_override: str | None = None,
        repo_map: str | None = None,
    ) -> AsyncIterator[Event]:
        sequence = self.accept()
        self._run_started_at = time.monotonic()
        self._heavy_tools_summarized = 0
        self._heavy_seq = 0
        _reset_usage = getattr(self.provider, "_reset_cumulative_usage", None)
        if callable(_reset_usage):
            _reset_usage()
        self._last_emitted_message = None
        _original_model = self.provider.model
        if model_override and model_override != self.provider.model:
            logger.info("Mode model override: %s → %s", self.provider.model, model_override)
            self.provider.model = model_override
        try:
            async for ev in self._process_prompt_impl(
                prompt,
                session_id,
                history,
                mode,
                plan_context,
                sequence,
                repo_map,
            ):
                yield ev
        finally:
            if model_override and model_override != _original_model:
                self.provider.model = _original_model

    async def _process_prompt_impl(
        self,
        prompt: str,
        session_id: str,
        history: list[Message],
        mode: str = BUILD_MODE,
        plan_context: str = "",
        sequence: int = 0,
        repo_map: str | None = None,
    ) -> AsyncIterator[Event]:
        self._compacted_this_turn = False
        self._compacted_message_count = 0
        provider_name = getattr(self.provider, "name", "")
        model = self.provider.model
        ws = self.config.workspace_root
        mode_config = AGENT_MODES.get(mode)
        allowed_tools = mode_config.allowed_tools if mode_config else None
        resolver = SchemaResolver(self.tool_registry, seed=build_mode_tool_seed(allowed_tools))
        if mode == PLAN_MODE:
            logger.info("PLAN MODE: using focused plan prompt (read + plan.md/todo.md)")
            system_prompt = build_plan_system_prompt(
                self.config.workspace_root,
                provider_name=provider_name,
                model_name=model,
                max_context_tokens=self.config.max_context_tokens,
            )
            registered_tools = set(resolver.active_names())
            openai_tools = resolver.openai_tools(PLAN_MODE)
            logger.info("Plan mode tools: %s", sorted(registered_tools))
        else:
            active_schemas = resolver.schemas(BUILD_MODE)
            system_prompt = build_system_prompt(
                self.config.workspace_root,
                mode,
                max_context_tokens=self.config.max_context_tokens,
                provider_name=provider_name,
                model_name=model,
            )
            registered_tools = set(resolver.active_names())
            openai_tools = schemas_to_openai_tools(active_schemas)
        self.context_manager.set_aux_tokens(
            min(resolver.schema_tokens(model), self._mode_tools_budget(model, mode))
        )
        _reflimit = reflection_error_limit(_get_model_context_window(model))
        messages = self.context_manager.build_messages(
            history,
            system_prompt,
            prompt,
            model,
            summary=self._summary,
            plan_block=plan_context,
            use_system_prompt=True,
            repo_map=repo_map,
            session_id=session_id,
            mode=mode,
        )
        base_len = len(messages)
        logger.info(
            "Context built: %d messages, system_prompt=%d chars", len(messages), len(system_prompt)
        )
        if self.context_manager.should_summarize(messages, model):
            _rebuild_holder: list[Any] = []
            async for _ev in self._summarize_and_rebuild(
                history,
                session_id,
                messages,
                result=_rebuild_holder,
                base_len=base_len,
                system_prompt=system_prompt,
                prompt=prompt,
                model=model,
                plan_context=plan_context,
                use_system_prompt=True,
                repo_map=repo_map,
                mode=mode,
            ):
                yield _ev
            messages = _rebuild_holder[0]
        if self.context_manager.is_context_exhausted(messages, model):
            yield r.turn_manifest(
                _build_manifest(
                    set(),
                    [],
                    False,
                    False,
                    "",
                    self.config.workspace_root,
                    [],
                    plan_mode=(mode == PLAN_MODE),
                ),
                session_id,
            )
            yield r.error(
                CONTEXT_EXHAUSTED_MESSAGE,
                session_id,
                code="CONTEXT_EXHAUSTED",
                action="retry",
                hint=CONTEXT_EXHAUSTED_HINT,
            )
            return
        if self.is_cancelled(sequence):
            yield r.turn_manifest(
                _build_manifest(
                    set(),
                    [],
                    False,
                    False,
                    "",
                    self.config.workspace_root,
                    [],
                    plan_mode=(mode == PLAN_MODE),
                ),
                session_id,
            )
            yield r.warning("Request was cancelled before starting", session_id, code="CANCELLED")
            return
        messages = self._apply_prompt_caching(messages)
        logger.info(
            "=== PROMPT READY FOR LLM session=%s mode=%s messages=%d ===",
            session_id,
            mode,
            len(messages),
        )
        logger.info("=== SYSTEM PROMPT (%d chars) ===\n%s", len(system_prompt), system_prompt)
        for i, msg in enumerate(messages):
            role = msg.get("role", "?")
            content = str(msg.get("content", ""))
            preview = content[:160].replace("\n", "\\n") if role != "system" and content else ""
            logger.info("--- MSG [%d] role=%s (len=%d) ---", i, role, len(content))
            if preview:
                logger.info("    preview=%s", preview)
        iteration = 0
        consecutive_failures = 0
        created_files: set[str] = set()
        executed_tool_names: set[str] = set()
        task_completed = False
        post_comp_iterations = 0
        files_edited: list[str] = []
        executed_calls: set[tuple[str, str]] = set()
        executed_results: dict[tuple[str, str], str] = {}
        failed_calls: set[tuple[str, str]] = set()
        stall_count = 0
        stall_finalized = False
        salvage_reason: str | None = None
        salvaged = False
        progress_steps: list[dict] = []
        warned_rejects: set[tuple[str, str]] = set()
        pending_skips: list[str] = []
        post_write_checks: list[dict] = []
        change_seq = 0
        last_evidence_seq = 0
        _total_completion_chars = 0
        active_tool_result_indices: list[int] = []
        def _session_todos() -> list[dict]:
            """Session-scoped todo snapshot for manifest remaining (QA-8)."""
            try:
                from server.agents.todo_state import get_todo_state

                return get_todo_state(session_id).snapshot()
            except Exception:
                return []

        def _with_manifest(ev: Event) -> Event:
            if isinstance(ev.data, dict) and "manifest" not in ev.data:
                ev.data["manifest"] = _build_manifest(
                    created_files,
                    files_edited,
                    task_completed,
                    stall_finalized,
                    self._last_emitted_message or "",
                    self.config.workspace_root,
                    post_write_checks,
                    plan_mode=(mode == PLAN_MODE),
                    todos=_session_todos(),
                )
            return ev

        def _param_detail(params: dict) -> str:
            """Short human snippet from tool params for progress labels."""
            import re

            if not isinstance(params, dict):
                return ""
            for key in ("command", "path", "filepath", "pattern", "query", "name", "url"):
                value = params.get(key)
                if isinstance(value, str) and value.strip():
                    flat = re.sub(r"\s+", " ", value.strip())
                    clipped = flat[:PROGRESS_DETAIL_MAX_CHARS]
                    return clipped + "\u2026" if len(flat) > PROGRESS_DETAIL_MAX_CHARS else clipped
            return ""

        def _emit_progress(tool_name: str, success: bool, detail: str = "") -> Event:
            """A PROGRESS event derived from an executed tool (QA-7).

            The label comes from the tool's activity label — never fabricated
            narration — and ``steps`` accumulates the turn's tool activity so the
            frontend ProgressBar can render a live checklist.
            """
            label = _activity_label(tool_name, len(progress_steps) + 1, detail)
            if progress_steps and progress_steps[-1].get("status") == "active":
                progress_steps[-1] = {
                    "label": label,
                    "status": "done" if success else "error",
                    "tool": tool_name,
                }
            else:
                progress_steps.append(
                    {
                        "label": label,
                        "status": "done" if success else "error",
                        "tool": tool_name,
                    }
                )
            done = sum(1 for s in progress_steps if s["status"] == "done")
            percent = round(done * 100 / len(progress_steps))
            return r.progress(
                percent, label, session_id, iteration=iteration, steps=list(progress_steps)
            )

        def _emit_progress_running(tool_name: str, detail: str = "") -> Event | None:
            """Mark a tool as in-flight before it executes (P6.1).

            The in-flight step counts as not-done, so the reported percent
            honestly reflects unfinished work instead of pinning at 100% while
            the turn keeps running.
            """
            label = _activity_label(tool_name, len(progress_steps) + 1, detail)
            progress_steps.append({"label": label, "status": "active", "tool": tool_name})
            done = sum(1 for s in progress_steps if s["status"] == "done")
            percent = round(done * 100 / len(progress_steps))
            return r.progress(
                percent, label, session_id, iteration=iteration, steps=list(progress_steps)
            )

        try:
            safety_iterations = self._resolve_safety_iterations(model)
            while iteration < safety_iterations:
                if self.is_cancelled(sequence):
                    yield r.turn_manifest(
                        _build_manifest(
                            created_files,
                            files_edited,
                            task_completed,
                            stall_finalized,
                            self._last_emitted_message or "",
                            self.config.workspace_root,
                            post_write_checks,
                            plan_mode=(mode == PLAN_MODE),
                            todos=_session_todos(),
                        ),
                        session_id,
                    )
                    yield r.warning("Request cancelled", session_id, code="CANCELLED")
                    return
                if task_completed and post_comp_iterations >= 1:
                    break
                iteration += 1
                if task_completed:
                    post_comp_iterations += 1
                token_info = self.context_manager.get_token_info(messages, model)
                if token_info.percent >= self.config.context_compaction_threshold and (
                    not self._compacted_this_turn or len(messages) > self._compacted_message_count
                ):
                    logger.warning(
                        "Context window %.1f%% full — summarizing", token_info.percent * 100
                    )
                    _rebuild_holder = []
                    async for ev in self._summarize_and_rebuild(
                        history,
                        session_id,
                        messages,
                        result=_rebuild_holder,
                        base_len=base_len,
                        system_prompt=system_prompt,
                        prompt=prompt,
                        model=model,
                        plan_context=plan_context,
                        use_system_prompt=True,
                        repo_map=repo_map,
                        mode=mode,
                    ):
                        yield ev
                    messages = _rebuild_holder[0]
                    token_info = self.context_manager.get_token_info(messages, model)
                    if token_info.percent > HARD_STOP_USAGE_RATIO:
                        yield _with_manifest(
                            r.error(
                                CONTEXT_EXHAUSTED_MESSAGE,
                                session_id,
                                code="CONTEXT_EXHAUSTED",
                                action="retry",
                                hint=CONTEXT_EXHAUSTED_HINT,
                            )
                        )
                        return
                for job in _pending_background_completions():
                    status = (
                        "completed" if job.exit_code == 0 else f"failed (exit code {job.exit_code})"
                    )
                    detail = f"Background job {job.id} {status}."
                    tail_source = (job.stderr or job.stdout or "").strip()
                    if tail_source:
                        detail += f"\nOutput (tail): {tail_source[-BG_OUTPUT_TAIL:]}"
                    messages.append({"role": "user", "content": detail})
                    yield r.warning(detail, session_id, code="BACKGROUND_COMPLETED")
                logger.info(
                    "Agent turn %d (dynamic stop) session=%s tokens=%.1f%%",
                    iteration,
                    session_id,
                    token_info.percent * 100,
                )
                stream_state = StreamState()
                finish_reason = FinishReason.STOP
                context_exceeded = False
                turn_tools = openai_tools
                turn_errored = False
                try:
                    _tool_choice = mode_config.tool_choice if mode_config else "auto"
                    async for event in stream_completion(
                        self.provider,
                        messages,
                        turn_tools,
                        session_id,
                        iteration,
                        stream_state,
                        tool_choice=_tool_choice,
                    ):
                        if event.kind == EventKind.WARNING and event.data.get("context_exceeded"):
                            context_exceeded = True
                        if event.kind == EventKind.ERROR:
                            turn_errored = True
                        yield event
                except ZenithError:
                    yield r.turn_manifest(
                        _build_manifest(
                            created_files,
                            files_edited,
                            task_completed,
                            stall_finalized,
                            self._last_emitted_message or "",
                            self.config.workspace_root,
                            post_write_checks,
                            plan_mode=(mode == PLAN_MODE),
                            todos=_session_todos(),
                        ),
                        session_id,
                    )
                    return
                if turn_errored:
                    consecutive_failures += 1
                    yield r.turn_manifest(
                        _build_manifest(
                            created_files,
                            files_edited,
                            task_completed,
                            stall_finalized,
                            self._last_emitted_message or "",
                            self.config.workspace_root,
                            post_write_checks,
                            plan_mode=(mode == PLAN_MODE),
                            todos=_session_todos(),
                        ),
                        session_id,
                    )
                    return
                if context_exceeded:
                    logger.info("Context exceeded at runtime — summarizing")
                    yield r.warning(
                        "Context window exceeded, summarizing and retrying...",
                        session_id,
                        code="CONTEXT",
                    )
                    _rebuild_holder = []
                    async for ev in self._summarize_and_rebuild(
                        history,
                        session_id,
                        messages,
                        result=_rebuild_holder,
                        base_len=base_len,
                        system_prompt=system_prompt,
                        prompt=prompt,
                        model=model,
                        plan_context=plan_context,
                        use_system_prompt=True,
                        repo_map=repo_map,
                        mode=mode,
                    ):
                        yield ev
                    messages = _rebuild_holder[0]
                    token_info = self.context_manager.get_token_info(messages, model)
                    if token_info.percent > HARD_STOP_USAGE_RATIO:
                        yield _with_manifest(
                            r.error(
                                "Context window exhausted even after summarization",
                                session_id,
                                code="CONTEXT_EXHAUSTED",
                                action="retry",
                                hint="Start a new session to free up context.",
                            )
                        )
                        return
                    continue
                finish_reason = getattr(self.provider, "_last_finish_reason", FinishReason.STOP)
                response_text = stream_state.response_text
                _total_completion_chars += len(response_text)
                native_tool_calls = getattr(self.provider, "_last_native_tool_calls", [])
                clean_response, tool_calls = UnifiedResponseFormatter.process_response(
                    response_text, native_tool_calls or None
                )
                logger.info(
                    "Agent turn %d response: %d chars, %d tool calls, clean=%d chars finish=%s",
                    iteration,
                    len(response_text),
                    len(tool_calls),
                    len(clean_response or ""),
                    finish_reason,
                )
                degenerate_response = _is_degenerate_message(clean_response)
                if (
                    clean_response
                    and not degenerate_response
                    and clean_response != self._last_emitted_message
                ):
                    yield r.message_event(
                        clean_response, session_id, partial=False, iteration=iteration
                    )
                    self._last_emitted_message = clean_response
                if finish_reason == FinishReason.LENGTH:
                    logger.info("FinishReason=LENGTH on turn %d — continuing response", iteration)
                    if iteration >= safety_iterations * 2:
                        yield _with_manifest(
                            r.error(
                                "Response length limit exceeded repeatedly",
                                session_id,
                                code="LENGTH_EXCEEDED",
                                action="retry",
                                hint="Try a shorter prompt or a model with a larger output budget.",
                            )
                        )
                        return
                    continue
                if not tool_calls:
                    if not clean_response and (not stream_state.full_response) and not turn_errored:
                        yield _with_manifest(
                            r.error(
                                "Model returned empty response.",
                                session_id,
                                code="EMPTY_RESPONSE",
                                recoverable=True,
                                action="retry",
                                hint="The model produced no output. Retry this prompt.",
                            )
                        )
                        return
                    task_completed = True
                    break
                if not self.tool_registry:
                    yield r.turn_manifest(
                        _build_manifest(
                            created_files,
                            files_edited,
                            task_completed,
                            stall_finalized,
                            self._last_emitted_message or "",
                            self.config.workspace_root,
                            post_write_checks,
                            plan_mode=(mode == PLAN_MODE),
                            todos=_session_todos(),
                        ),
                        session_id,
                    )
                    yield _with_manifest(r.error("No tool registry available", session_id))
                    return
                if self.tool_registry:
                    for tc in tool_calls:
                        t_name = tc.get("tool")
                        if not t_name:
                            continue
                        if t_name == GET_TOOL_DEFINITION_TOOL:
                            target = (tc.get("params") or {}).get("tool_name")
                            if target and resolver.request_tool(target):
                                if mode == PLAN_MODE and target in (BASH_TOOL, TERMINAL_TOOL):
                                    yield r.warning(
                                        f"Tool escalation denied: '{target}' cannot be promoted in plan mode.",
                                        session_id,
                                        code="PLAN_MODE_TOOL_ESCALATION_DENIED",
                                    )
                                    continue
                                logger.info(
                                    "Discovery: loaded tool '%s' via get_tool_definition", target
                                )
                        elif t_name not in registered_tools and resolver.request_tool(t_name):
                            logger.info(
                                "Dynamic tool escalation: promoted tool '%s' into active schema",
                                t_name,
                            )
                    new_active = resolver.active_names()
                    if set(new_active) != registered_tools:
                        prev_names = set(registered_tools)
                        registered_tools = set(new_active)
                        openai_tools = resolver.openai_tools(mode)
                        self.context_manager.set_aux_tokens(
                            min(resolver.schema_tokens(model), self._mode_tools_budget(model, mode))
                        )
                        logger.info(
                            "Tool set changed mid-turn: added=%s removed=%s",
                            sorted(registered_tools - prev_names),
                            sorted(prev_names - registered_tools),
                        )
                valid_calls, invalid_calls = validate_tool_calls(tool_calls, registered_tools)
                invalid_names = [str(tc.get("tool") or tc) for tc in invalid_calls]
                if invalid_names:
                    yield r.warning(
                        f"Hallucinated tools ignored: {', '.join(invalid_names)}",
                        session_id,
                        code="INVALID_TOOLS",
                    )
                if not valid_calls:
                    messages.append({"role": "assistant", "content": response_text or ""})
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Tool calls for non-existent tools: {', '.join(invalid_names)}. Available: {', '.join(sorted(registered_tools))}.",
                        }
                    )
                    continue
                messages.append({"role": "assistant", "content": response_text or ""})
                if _all_calls_repeat(valid_calls, executed_calls, self.config.workspace_root):
                    _repeat_text = (clean_response or "").strip()
                    if (
                        _repeat_text
                        and len(_repeat_text) >= SUMMARY_MIN_CHARS
                        and (created_files or files_edited)
                    ):
                        task_completed = True
                        logger.info(
                            "Turn finalized at repeat-detection: summary + only repeated calls "
                            "after file work (%d file(s)).",
                            len(created_files),
                        )
                        break
                    if iteration > 1:
                        logger.debug(
                            "All requested calls already executed this turn; falling through so the "
                            "per-call loop can skip them and the stall handler can guide the model."
                        )
                if task_completed:
                    yield r.warning(
                        "Model emitted tool calls after signaling completion; finalizing the turn.",
                        session_id,
                        code="STALL",
                        extra={"skipped_tool_calls": [tc.get("tool") for tc in valid_calls]},
                    )
                    break
                stop_turn = False
                skipped_calls: list[str] = []
                newly_executed = False

                # ---- WP5 Phase 4b: parallel crewmate fan-out -----------------
                # Several independent explore calls in one turn are dispatched
                # concurrently (the tool's own semaphore caps width); results
                # land in ``preexecuted`` and flow through the standard
                # sequential handler below, so isolation, digests, duplicate
                # feedback and tracking all apply unchanged.
                preexecuted: dict[int, tuple[ToolResult, int]] = {}
                merged_fanout_dups: set[int] = set()
                _fanout: list[tuple[int, tuple[str, str], dict]] = []
                _seen_fanout: set[tuple[str, str]] = set()
                for _idx, _tc in enumerate(valid_calls):
                    if _tc["tool"] != EXPLORE_TOOL:
                        continue
                    _p = normalize_file_params(_tc.get("params", {}), EXPLORE_TOOL)
                    _sig = _call_signature("explore", _p, self.config.workspace_root)
                    if _sig in executed_calls or _sig in _seen_fanout:
                        if _sig in _seen_fanout:
                            merged_fanout_dups.add(_idx)
                        continue
                    _seen_fanout.add(_sig)
                    _fanout.append((_idx, _sig, _p))
                if len(_fanout) >= 2:
                    logger.info(
                        "Parallel crewmate fan-out: %d explore missions in one turn",
                        len(_fanout),
                    )
                    yield _emit_progress_running(
                        EXPLORE_TOOL,
                        f"fanning out {len(_fanout)} crewmates in parallel",
                    )
                    _gathered = await asyncio.gather(
                        *(
                            execute_tool(
                                self.tool_registry,
                                EXPLORE_TOOL,
                                _p,
                                ws,
                                mode,
                            )
                            for _i, _s, _p in _fanout
                        ),
                        return_exceptions=True,
                    )
                    for (_idx, _sig, _p), _outcome in zip(_fanout, _gathered):
                        if isinstance(_outcome, BaseException):
                            preexecuted[_idx] = (
                                ToolResult(success=False, error=str(_outcome)),
                                0,
                            )
                        else:
                            preexecuted[_idx] = _outcome

                for call_index, tc in enumerate(valid_calls):
                    tool_name = tc["tool"]
                    tool_params = normalize_file_params(tc.get("params", {}), tc["tool"])
                    sig = _call_signature(tool_name, tool_params, self.config.workspace_root)
                    if call_index in merged_fanout_dups:
                        # Identical to a sibling explore in this fan-out: the
                        # kept mission's report covers it.
                        skipped_calls.append(f"{tool_name}({_params_label(tool_params)}) [merged]")
                        pending_skips.append(skipped_calls[-1])
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "[Merged] This explore call is identical to another "
                                    "in the same fan-out; its report covers this "
                                    "objective. Continue with remaining work."
                                ),
                            }
                        )
                        continue
                    if sig in executed_calls and tool_name not in POLL_TOOLS:
                        # WP2: duplicate feedback is delivered IN-BAND as a
                        # result-shaped message in the call's own slot — never
                        # as a synthetic user note the model cannot attribute
                        # to its own action.
                        failed = sig in failed_calls
                        skipped_calls.append(
                            f"{tool_name}({_params_label(tool_params)})"
                            + (" [failed]" if failed else "")
                        )
                        if failed:
                            guidance = (
                                f"Duplicate call blocked: this exact {tool_name} call already FAILED "
                                "earlier this turn with identical parameters. Repeating it will fail "
                                "identically - change the approach or fix the parameters."
                            )
                        else:
                            guidance = (
                                f"Duplicate call blocked: this exact {tool_name} call already ran "
                                "earlier this turn with identical parameters and returned the "
                                "result below. Do not re-run it - build on the previous result or "
                                "change parameters."
                            )
                        parts = [guidance]
                        prior = executed_results.get(sig)
                        if prior:
                            capped, _ = compact_tool_output(
                                prior, max_output=DUP_RESULT_PREVIEW_CHARS
                            )
                            parts.append("Previous result:\n" + capped)
                        messages.append(
                            {"role": "user", "content": "\n\n".join(parts), "duplicate_of": sig}
                        )
                        continue
                    reject_msg = validate_tool_rejection(tool_name, tool_params, created_files, ws)
                    if tool_name in ("bash", "terminal") and (not reject_msg):
                        from server.toolkit.command_safety import assess_command

                        assessment = assess_command(tool_params.get("command", ""))
                        if assessment.is_risky and not self.config.auto_risky:
                            reject_msg = f"Command denied: {tool_params.get('command', '')} ({assessment.reason})"
                    if tool_name == FILE_WRITE_TOOL and (not reject_msg):
                        target = tool_params.get("filepath") or tool_params.get("path") or ""
                        if target:
                            resolved = validate_path(target, ws)
                            if resolved is not None and resolved.exists():
                                if not self.config.auto_overwrite:
                                    reject_msg = (
                                        f"File overwrite denied: '{target}' already exists. Pass "
                                        f"overwrite=true to replace it, or delete it first."
                                    )
                                else:
                                    tool_params[FILE_OVERWRITE_PARAM] = True
                    if tool_name == FILE_DELETE_TOOL and (not reject_msg):
                        target = tool_params.get("path") or ""
                        if target:
                            resolved = validate_path(target, ws)
                            if (
                                resolved is not None
                                and resolved.exists()
                                and not self.config.auto_risky
                            ):
                                reject_msg = f"File delete denied: '{target}'."
                    if reject_msg:
                        reject_sig = _call_signature(
                            tool_name, tool_params, self.config.workspace_root
                        )
                        if reject_sig not in warned_rejects:
                            warned_rejects.add(reject_sig)
                            yield r.warning(
                                f"Tool '{tool_name}' rejected: {reject_msg}",
                                session_id,
                                code="REJECTED",
                            )
                        messages.append(
                            {"role": "user", "content": f"[Tool rejected] {reject_msg}"}
                        )
                        consecutive_failures += 1
                        if consecutive_failures >= _reflimit:
                            yield _with_manifest(
                                r.error(
                                    f"Too many errors ({consecutive_failures}).",
                                    session_id,
                                    code="REFLECTION_LIMIT",
                                    recoverable=True,
                                )
                            )
                            return
                        continue
                    yield r.tool_call(tool_name, tool_params, session_id)
                    newly_executed = True
                    executed_tool_names.add(tool_name)
                    yield _emit_progress_running(tool_name, _param_detail(tool_params))
                    explore_crewmate = (
                        self._explore_spawn_event(session_id, tool_params)
                        if tool_name == EXPLORE_TOOL
                        else None
                    )
                    if explore_crewmate is not None:
                        # WP5: light the crewmate card the moment a crewmate
                        # departs; completion is stamped on its result below.
                        yield explore_crewmate
                    _pre = preexecuted.pop(call_index, None)
                    if _pre is not None:
                        # Fan-out result already fetched concurrently (Phase 4b).
                        result, duration_ms = _pre
                    else:
                        result, duration_ms = await execute_tool(
                            self.tool_registry,
                            tool_name,
                            tool_params,
                            ws,
                            mode,
                        )
                    if explore_crewmate is not None:
                        yield self._explore_settle_event(session_id, explore_crewmate.data, result)
                    _model_ctx = _get_model_context_window(model)
                    result_limit = _dynamic_max_output(_model_ctx)
                    _compacted, cstats = compact_tool_output(
                        result.output or "", max_output=result_limit
                    )
                    metadata = build_tool_metadata(tool_name, tool_params, result, duration_ms, ws)
                    if cstats.chars_removed > 0:
                        metadata["trim"] = {
                            "charsRemoved": cstats.chars_removed,
                            "tokensSaved": cstats.tokens_saved,
                            "reason": cstats.reason,
                        }
                    yield r.tool_result(
                        tool_name,
                        result.success,
                        session_id,
                        output=result.output or "",
                        error=result.error or "",
                        metadata=metadata,
                    )
                    yield _emit_progress(tool_name, result.success, _param_detail(tool_params))
                    if result.stop_turn:
                        logger.info("Tool '%s' requested stop_turn", tool_name)
                        stop_turn = True
                    if not result.success:
                        consecutive_failures += 1
                        if consecutive_failures >= _reflimit:
                            yield _with_manifest(
                                r.error(
                                    f"Too many errors ({consecutive_failures}).",
                                    session_id,
                                    code="REFLECTION_LIMIT",
                                    recoverable=True,
                                )
                            )
                            return
                    else:
                        consecutive_failures = 0
                    _ti = self.context_manager.get_token_info(messages, model)
                    _remaining = _ti.total - _ti.used
                    _reserve = _adaptive_reserve(model, _ti.total)
                    if _remaining <= _reserve and _remaining > 0:
                        logger.warning(
                            "Context approaching limit (%.0f%%), summarizing...", _ti.percent * 100
                        )
                        _rebuild_holder = []
                        async for ev in self._summarize_and_rebuild(
                            history,
                            session_id,
                            messages,
                            result=_rebuild_holder,
                            base_len=base_len,
                            system_prompt=system_prompt,
                            prompt=prompt,
                            model=model,
                            plan_context=plan_context,
                            use_system_prompt=True,
                            repo_map=repo_map,
                            mode=mode,
                        ):
                            yield ev
                        messages = _rebuild_holder[0]
                        _ti2 = self.context_manager.get_token_info(messages, model)
                        if _ti2.percent > HARD_STOP_USAGE_RATIO:
                            yield _with_manifest(
                                r.error(
                                    CONTEXT_EXHAUSTED_MESSAGE,
                                    session_id,
                                    code="CONTEXT_EXHAUSTED",
                                    recoverable=True,
                                    action="retry",
                                    hint=CONTEXT_EXHAUSTED_HINT,
                                )
                            )
                            return
                        yield r.warning(
                            "Context summarized, continuing", session_id, code="CONTEXT"
                        )
                    executed_calls.add(sig)
                    if not result.success:
                        failed_calls.add(sig)
                    if result.success:
                        p = tool_params.get("filepath") or tool_params.get("path") or ""
                        if p:
                            if tool_name == FILE_WRITE_TOOL:
                                created_files.add(p)
                            if tool_name in (FILE_EDIT_TOOL, FILE_WRITE_TOOL):
                                files_edited.append(p)
                            change_seq += 1
                        if (
                            change_seq > 0
                            and tool_name not in (FILE_WRITE_TOOL, FILE_EDIT_TOOL)
                            and len(post_write_checks) < MANIFEST_CHECKS_CAP
                        ):
                            post_write_checks.append(
                                {
                                    "tool": tool_name,
                                    "output_len": len(result.output or ""),
                                    "exit_code": (result.metadata or {}).get("exit_code"),
                                    "seq": change_seq,
                                }
                            )
                            if (result.output or "") != "":
                                last_evidence_seq = change_seq
                    for ev in await post_execution_hooks(
                        tool_name, tool_params, result, ws, session_id
                    ):
                        yield ev
                    digest_str = format_tool_digest(tool_name, tool_params, result)
                    content = format_tool_result(tool_name, result, result_limit)
                    if not result.success:
                        # Error guidance rides on the result itself (one message
                        # per action), never as a separate synthetic user turn.
                        content += (
                            f"\nThe {tool_name} call failed - respond to the error above "
                            "rather than repeating the same call."
                        )
                        if tool_name == FILE_EDIT_TOOL:
                            content += (
                                " The target text did not match the file's current content: "
                                "read the file with file_read, then re-apply the edit against "
                                "the exact current content."
                            )
                    messages.append(
                        {
                            "role": "user",
                            "content": content,
                            "digest": digest_str,
                        }
                    )
                    active_tool_result_indices.append(len(messages) - 1)
                    if len(active_tool_result_indices) > EPHEMERAL_TOOL_WINDOW_SIZE:
                        for old_idx in active_tool_result_indices[:-EPHEMERAL_TOOL_WINDOW_SIZE]:
                            if 0 <= old_idx < len(messages):
                                old_msg = messages[old_idx]
                                if "digest" in old_msg and not old_msg.get("is_digested"):
                                    old_msg["content"] = old_msg["digest"]
                                    old_msg["is_digested"] = True
                    if tool_name == FILE_WRITE_TOOL and result.success:
                        p_written = tool_params.get("filepath") or tool_params.get("path") or ""
                        if p_written:
                            _strip_write_payload_from_assistant_messages(messages, p_written)
                    executed_results[sig] = messages[-1]["content"]
                if skipped_calls:
                    for s in skipped_calls:
                        if s not in pending_skips:
                            pending_skips.append(s)
                if skipped_calls and not newly_executed and not task_completed:
                    stall_count += 1
                    current_text = (clean_response or "").strip()
                    if (
                        current_text
                        and len(current_text) >= SUMMARY_MIN_CHARS
                        and not created_files
                        and not files_edited
                        and not _incomplete_todo_titles(_session_todos())
                    ):
                        # Answer-completion hatch (AGENT_RELIABILITY_PLAN P1.1):
                        # the model delivered a substantive final answer while
                        # every emitted call was a duplicate. With no file work
                        # and nothing pending, this is a successful answer-only
                        # turn — finalize cleanly instead of forcing a stall.
                        task_completed = True
                        logger.info(
                            "Turn finalized: delivered a substantive answer (%d chars); "
                            "all calls were duplicates and no work is pending.",
                            len(current_text),
                        )
                        break
                    if (
                        current_text
                        and len(current_text) >= SUMMARY_MIN_CHARS
                        and (created_files or files_edited)
                        and _has_verification_evidence(post_write_checks, after_seq=change_seq)
                    ):
                        task_completed = True
                        logger.info(
                            "Turn finalized: model wrote a final summary after completing "
                            "file work (%d file(s) changed, verification evidence present).",
                            len(created_files) + len(files_edited),
                        )
                        break
                    if (
                        (created_files or files_edited)
                        and last_evidence_seq >= change_seq
                        and last_evidence_seq > 0
                    ):
                        task_completed = True
                        logger.info(
                            "Turn finalized: file changes implemented and re-verification "
                            "produced evidence; no outstanding work."
                        )
                        break
                    # No coaching ladder: duplicate feedback already reached the
                    # model in-band (per-call blocked results). After
                    # STALL_FINALIZE_AFTER_ITERATIONS consecutive do-nothing
                    # iterations, stop — physics, not behavior shaping.
                    if stall_count >= STALL_FINALIZE_AFTER_ITERATIONS:
                        task_completed = True
                        stall_finalized = True
                        yield r.warning(
                            "No new tool work for several consecutive iterations; finalizing the turn.",
                            session_id,
                            code="STALL",
                        )
                        break
                elif newly_executed:
                    stall_count = 0
                if stop_turn:
                    logger.info("Stopping turn: tool requested stop_turn")
                    task_completed = True
                    break
                if files_edited:
                    auto_commit(ws, files_edited)
                    files_edited.clear()
            else:
                yield _with_manifest(
                    r.error(
                        f"Safety net exceeded ({safety_iterations} iterations)",
                        session_id,
                        code="MAX_ITERATIONS",
                    )
                )
                # WP3: the iteration budget is exhausted, not the work — the
                # finalization path below salvages a best-effort answer.
                salvage_reason = f"iteration budget exhausted ({safety_iterations} steps)"
        finally:
            pass
        # ---- WP3: salvage pass (single choke point) --------------------------
        # Harness-forced exits (stall cap / loop cap / iteration budget) must
        # never end in an empty response. If the model already delivered a
        # substantive answer, this is a no-op. User cancellations and context-
        # exhaustion exits return earlier and never reach this stage.
        if (salvage_reason or stall_finalized) and len(
            (self._last_emitted_message or "").strip()
        ) < SUMMARY_MIN_CHARS:
            async for ev in self._salvage_final_answer(
                session_id=session_id,
                messages=messages,
                model=model,
                reason=salvage_reason or "no recent progress",
                iteration=iteration,
            ):
                yield ev
            salvaged = True
        final_summary = (self._last_emitted_message or "").strip()
        legit_completion = task_completed and not stall_finalized
        quiet_completion = legit_completion and len(final_summary) >= SUMMARY_MIN_CHARS
        if pending_skips and not quiet_completion:
            shown = ", ".join(pending_skips[:SKIP_WARNING_CAP])
            omitted = len(pending_skips) - SKIP_WARNING_CAP
            if omitted > 0:
                shown += f", +{omitted} more"
            yield r.warning(
                "Skipped calls already completed with identical params this turn "
                "(or blocked as re-writes): " + shown,
                session_id,
                code="SKIPPED_CALLS",
            )
        token_info = self.context_manager.get_token_info(messages, model)
        cum_usage: dict = getattr(self.provider, "_cumulative_usage", {})
        prompt_tokens = cum_usage.get("prompt_tokens") or token_info.used
        completion_tokens = cum_usage.get("completion_tokens") or max(
            1, _total_completion_chars // 4
        )
        is_estimated = cum_usage.get("total_tokens", 0) == 0
        tier_breakdown = self.context_manager.token_breakdown(messages).to_dict()
        if mode == BUILD_MODE and executed_tool_names and (not created_files):
            _file_tools_attempted = any(name in FILE_MUTATING_TOOLS for name in executed_tool_names)
            if _file_tools_attempted:
                yield r.warning(
                    "Build completed but no files were created. The model output text instead of using file_write.",
                    session_id,
                    code="NO_FILES_CREATED",
                )
        success_message = "Request processed successfully"
        if stall_finalized or salvaged:
            created = ", ".join(sorted(created_files)) or "none"
            success_message = (
                f"Stopped after {iteration} iterations: the model stopped making progress "
                f"(reason: {salvage_reason or 'no recent progress'}). "
                f"Files written: {created}."
            )
            if salvaged:
                success_message += (
                    " A best-effort summary was generated from the gathered evidence."
                )
        if (created_files or files_edited) and not _has_verification_evidence(post_write_checks):
            success_message += (
                " Files changed but not verified: no successful tool produced output after "
                "the changes to confirm the result. Use file_read to inspect the files or "
                "run the app/tests to verify they work."
            )
        manifest = _build_manifest(
            created_files,
            files_edited,
            task_completed,
            stall_finalized,
            self._last_emitted_message or "",
            self.config.workspace_root,
            post_write_checks,
            plan_mode=(mode == PLAN_MODE),
            todos=_session_todos(),
        )
        yield r.turn_manifest(manifest, session_id)
        if mode == PLAN_MODE:
            # Plan-mode artifact contract: never report a successful, complete
            # plan when the writable artifact (plan.md) was not actually written
            # — the output must be honest about the miss.
            missing = (manifest.get("plan_artifacts") or {}).get("missing") or []
            # Only plan.md is the blocking artifact: todo.md absence is reported
            # but does not invalidate a plan that was actually written.
            if "plan.md" in missing and not manifest.get("stalled"):
                success_message += (
                    "\n[Not implemented] Plan artifact not written: plan.md. "
                    "The plan output above is a proposal only; run in plan mode "
                    "again to write plan.md."
                )
        _started_at = getattr(self, "_run_started_at", None)
        elapsed_ms = (
            round((time.monotonic() - _started_at) * 1000) if _started_at is not None else None
        )
        yield _with_manifest(
            r.success(
                success_message,
                session_id,
                iteration,
                {
                    # Context occupancy (composed messages) — drives the gauge.
                    "used": token_info.used,
                    "remaining": token_info.remaining,
                    "total": token_info.total,
                    "percent": round(token_info.percent, 3),
                    # Run/API usage (cumulative provider spend) — telemetry only.
                    "runTotal": cum_usage.get("total_tokens", 0),
                    "runPrompt": cum_usage.get("prompt_tokens", 0),
                    "runCompletion": cum_usage.get("completion_tokens", 0),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cached_tokens": cum_usage.get("cached_tokens", 0),
                    "cache_creation_tokens": cum_usage.get("cache_creation_tokens", 0),
                    "estimated": is_estimated,
                    "windowEstimated": bool(
                        getattr(self.context_manager, "context_window_estimated", False)
                    ),
                    "mode": mode,
                    "ttft_ms": getattr(self.provider, "_last_ttft_ms", None),
                    "contextBreakdown": tier_breakdown,
                    "heavy_tools_summarized": self._heavy_tools_summarized,
                    "cache_hit_rate": round(
                        cum_usage.get("cached_tokens", 0) / max(prompt_tokens, 1),
                        4,
                    ),
                },
                elapsed_ms=elapsed_ms,
            )
        )

    async def _maybe_summarize(self, history, session_id, messages=None, reason="automatic"):
        """Route one automatic compaction through the canonical service.

        Events are forwarded to the caller via the generator; the outcome is
        kept on ``self._last_compaction_outcome``.
        """
        emitted: list[Event] = []

        async def _emit(ev: Event) -> None:
            emitted.append(ev)

        outcome = await self._get_compaction_service().compact(
            session_id=session_id,
            history=history,
            messages=messages,
            trigger=CompactionTrigger.AUTOMATIC,
            reason=reason,
            previous_summary=self._summary,
            emit=_emit,
        )
        self._last_compaction_outcome = outcome
        if not outcome.failed and not outcome.skipped:
            self._summary = outcome.summary or self._summary
        for ev in emitted:
            yield ev

    def _rebuild_messages(
        self,
        messages: list[dict],
        base_len: int,
        history: list[Message],
        system_prompt: str,
        prompt: str,
        model: str,
        plan_context: str,
        use_system_prompt: bool,
        repo_map: str | None,
        session_id: str | None = None,
        mode: str = BUILD_MODE,
    ) -> list[dict]:
        live_tail = messages[base_len:]
        rebuilt = self.context_manager.build_messages(
            history,
            system_prompt,
            prompt,
            model,
            summary=self._summary,
            plan_block=plan_context,
            use_system_prompt=use_system_prompt,
            repo_map=repo_map,
            session_id=session_id,
            mode=mode,
        )
        if live_tail:
            compacted_tail = []
            for msg in live_tail:
                if not isinstance(msg, dict):
                    continue
                compacted_tail.append(dict(msg))
            compact_live_tail(compacted_tail)

            rebuilt.extend(compacted_tail)
            rebuilt.append(
                {
                    "role": "user",
                    "content": "Continue if you have next steps, or stop and ask for clarification for how to proceed.",
                }
            )
            logger.info(
                "Replayed compacted live turn after compaction: %d messages", len(live_tail)
            )
        sanitized = [m for m in rebuilt if isinstance(m, dict)]
        dropped = len(rebuilt) - len(sanitized)
        if dropped:
            logger.warning(
                "Rebuild dropped %d non-dict message(s): %r",
                dropped,
                [type(m).__name__ for m in rebuilt if not isinstance(m, dict)],
            )
        return sanitized

    async def _summarize_and_rebuild(
        self,
        history,
        session_id,
        messages,
        *,
        result,
        base_len,
        system_prompt,
        prompt,
        model,
        plan_context,
        use_system_prompt,
        repo_map,
        mode: str = BUILD_MODE,
    ) -> AsyncIterator[Event]:
        async for ev in self._maybe_summarize(history, session_id, messages):
            yield ev
        outcome = self._last_compaction_outcome
        if outcome is None or outcome.failed or outcome.skipped:
            
            result.append(list(messages))
            return
        cut = max(0, outcome.cut)
        tail_history = history[cut:] if cut > 0 else []
        self._compacted_this_turn = True
        result.append(
            self._rebuild_messages(
                messages,
                base_len,
                tail_history,
                system_prompt,
                prompt,
                model,
                plan_context,
                use_system_prompt,
                repo_map,
                session_id=session_id,
                mode=mode,
            )
        )
        self._compacted_message_count = len(result[-1])

    def _get_tool_schemas(self) -> list[dict]:
        return self.tool_registry.get_schemas() if self.tool_registry else []

    def _get_tool_names(self) -> list[str]:
        return self.tool_registry.list_tools() if self.tool_registry else []

    def _apply_prompt_caching(self, messages: list[dict]) -> list[dict]:
        if not messages:
            return messages
        provider_name = getattr(self.provider, "name", "") or ""
        catalog = self._catalog_for_provider(provider_name)
        if not catalog.get("supports_prompt_caching", False):
            return messages
        if catalog.get("adapter") == "gemini":
            return messages
        cached = [dict(msg) for msg in messages]
        prefix_length = self.context_manager.required_prefix_length()
        if 0 < prefix_length <= len(cached):
            cached[prefix_length - 1]["cache_control"] = {"type": "ephemeral"}
        return cached

    @staticmethod
    def _catalog_for_provider(provider_name: str) -> dict:
        try:
            from server.storage import load_catalog

            return load_catalog().get("providers", {}).get(provider_name) or {}
        except Exception:
            return {}

