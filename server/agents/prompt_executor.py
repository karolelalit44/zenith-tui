from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import server.providers.responder as r
from server.agents.context import ContextManager
from server.agents.delegation import (
    CaptainOrchestrator,
    RepositoryIntelligenceCache,
    SpecialistRegistry,
)
from server.agents.recovery import RecoverableAgentLoop
from server.agents.run_state import (
    from_dict,
    merge_run_state,
    update_from_event,
)
from server.agents.running_summary import RunningSummaryScheduler
from server.agents.crewmate_loop import CrewmateLoop
from server.config.constants import (
    ATTACHMENT_MAX_FILE,
    ATTACHMENT_MAX_TOTAL,
    BUILD_MODE,
    DEFAULT_CONTEXT_WINDOW,
    EXPLORE_DELEGATION_PROACTIVE,
    HANDOFF_PLACEHOLDER_CANCELLED,
    HANDOFF_PLACEHOLDER_ERROR,
    HANDOFF_PLACEHOLDER_NO_SUMMARY,
    PLAN_MODE,
    TERMINAL_STATUS_CANCELLED,
    TERMINAL_STATUS_COMPLETED,
    TERMINAL_STATUS_ERROR,
)
from server.config.settings import AGENT_MODES
from server.domain.domain import SessionState
from server.domain.events import Event, EventKind
from server.domain.message import Message
from server.storage.usage_store import FileTokenUsageRepository

if TYPE_CHECKING:
    from server.api.handlers import MethodHandlers
    from server.config.settings import AppSettings
    from server.providers.base import BaseProvider
    from server.skills.loader import SkillLoader
    from server.storage.session_store import FileMessageRepository, FileSessionRepository
    from server.toolkit.registry import ToolRegistry
logger = logging.getLogger(__name__)

# When a worker turn produced files and its raw last-emitted text is this long, fold it into
# a weak-model summary so the persisted assistant hand-off stays compact (§3.3 of the design).
_HANDOFF_SUMMARY_CHARS = 800
# Hard ceiling on the persisted assistant message. Guards against repeated
# tool/reasoning noise ever becoming the canonical message (evidence-aware
# finalization, QA-3).
_HANDOFF_MAX_CHARS = 4000


def _read_file_head(path: str | Path) -> bytes:
    with open(path, "rb") as f:
        return f.read(8192)


def _read_file_text(path: str | Path) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


async def read_attachment(path: str, workspace_root: str | Path) -> tuple[str | None, str | None]:
    try:
        root = Path(workspace_root).resolve()
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = root / candidate
        candidate = candidate.resolve()
        if not candidate.is_relative_to(root):
            return (None, "path escapes workspace")
        if not candidate.is_file():
            return (None, "file not found")
        size = candidate.stat().st_size
        if size > ATTACHMENT_MAX_FILE:
            return (None, f"file too large ({size} bytes, max {ATTACHMENT_MAX_FILE})")
        head = await asyncio.to_thread(_read_file_head, candidate)
        if b"\x00" in head:
            return (None, "binary file")
        text = await asyncio.to_thread(_read_file_text, candidate)
        return (text, None)
    except OSError as e:
        return (None, f"read failed: {e}")


def _turn_manifest_from_events(collected_events: list[Event]) -> dict | None:
    """Extract the last TURN_MANIFEST payload (the crafted created/modified/verified record)."""
    manifest: dict | None = None
    for ev in collected_events or []:
        if ev.kind == EventKind.TURN_MANIFEST and isinstance(ev.data, dict):
            m = ev.data.get("manifest")
            if isinstance(m, dict):
                manifest = m
    return manifest


def _build_crafted_handoff(manifest: dict | None, response_text: str) -> str | None:
    """Build a deterministic, terse assistant hand-off from the turn manifest.

    Shape: `Created: <files> | Modified: <files> | Verified: <bool>` then the model's own
    last emitted text as the body. Rich enough for the next prompt, never empty.
    Returns ``None`` when nothing of substance happened and there is no body text.
    """
    parts: list[str] = []
    if manifest:
        # Plan-mode artifact contract: a plan turn that did not write plan.md has
        # remaining work, surfaced in the hand-off regardless of prose.
        missing_plan = (manifest.get("plan_artifacts") or {}).get("missing") or []
        if missing_plan:
            parts.append("Plan artifacts not written: " + ", ".join(missing_plan))
        created = [str(p) for p in (manifest.get("created") or [])]
        modified = [str(p) for p in (manifest.get("modified") or [])]
        if created:
            parts.append("Created: " + ", ".join(created))
        if modified:
            parts.append("Modified: " + ", ".join(modified))
        if created or modified:
            parts.append("Verified: " + ("true" if manifest.get("verified") else "false"))
        remaining = manifest.get("remaining") or []
        if remaining:
            snippet = (str(remaining[0]) or "").strip()
            if snippet:
                parts.append("Remaining: " + snippet[:160])
    header = " | ".join(parts)
    body = (response_text or "").strip()
    # The manifest is authoritative: a body that asserts work the manifest
    # proves never happened is corrected before it can be persisted/rendered.
    # Correction requires an actual manifest that shows no work — with no
    # manifest there is no evidence to contradict, so prose is left untouched.
    # A plan.md miss (QA-6.5) is a blocking correction even when other work
    # (e.g. todo.md) happened.
    missing_plan = (manifest or {}).get("plan_artifacts") or {}
    blocking = (
        "plan.md" in (missing_plan.get("missing") or [])
        if isinstance(missing_plan, dict)
        else False
    )
    if manifest is not None and (not _did_work(manifest) or blocking):
        body = _rewrite_false_completion_claim(body, manifest)
    if header and body:
        return f"{header}\n\n{body}"
    if body:
        return body
    return header or None


def _did_work(manifest: dict | None) -> bool:
    if not manifest:
        return False
    return bool((manifest.get("created") or []) or (manifest.get("modified") or []))


# ---------------------------------------------------------------------------
# Evidence-aware finalization: the execution manifest is authoritative. A claim
# in the model's prose (``Created X``, ``Fixed the bug``, ``Done``) that the
# manifest does not back up is rewritten to a factual correction so the
# persisted assistant message never asserts work that did not happen.
# ---------------------------------------------------------------------------

# Confident work-claims / completion signals that would be false when the
# manifest records no created/modified files. Anchored to word boundaries and
# matched case-insensitively.
_COMPLETION_CLAIM_PATTERNS = (
    r"\b(?:created|wrote|written|wrote out)\s+(?:the\s+)?(?:file|files)",
    r"\b(?:created|wrote)\s+[`']?[\w./\\-]+\.(?:py|ts|tsx|js|jsx|json|toml|yaml|yml|md|txt|css|html)\b",
    r"\b(?:fixed|resolved|solved|implemented|completed|finished|done)\b",
    r"\bcreated\b.{0,80}\b(?:file|file[s]?)\b",
    r"\bnew\s+file\b",
)
# A negative claim (``no file was created``) must not be corrected.
_NEGATIVE_CLAIM_PATTERNS = (
    r"\b(?:not|no)\s+(?:able\s+to\s+)?(?:create|write|implement|fix|resolve|complete|done)\b",
    r"\bcouldn'?t\b",
    r"\bwas\s+unable\b",
    r"\bfailed\b",
    r"\bdid\s+not\b",
)


def plan_claim_is_negative(response_text: str) -> bool:
    """True when ``response_text`` explicitly denies completing the plan."""
    text = (response_text or "").strip()
    if not text:
        return True
    for pattern in _NEGATIVE_CLAIM_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False


def _claim_contradicts_evidence(response_text: str) -> bool:
    """True when ``response_text`` asserts work the manifest can prove never happened."""
    text = (response_text or "").strip()
    if not text:
        return False
    for negative in _NEGATIVE_CLAIM_PATTERNS:
        if re.search(negative, text, flags=re.IGNORECASE):
            return False
    for pattern in _COMPLETION_CLAIM_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False


def _rewrite_false_completion_claim(response_text: str, manifest: dict | None) -> str:
    """Prefix a completion claim that contradicts the empty manifest.

    Returns a corrected body of the form:
        "[Not implemented] <original claim>. Evidence: no file was created or modified in this turn."
    In plan mode, the correction names the missing plan artifact(s) when the
    turn claimed a complete plan but did not write plan.md/todo.md.
    """
    text = (response_text or "").strip()
    if not text or text.startswith("[Not implemented]"):
        return text
    # Plan-mode artifact contract (QA-6.5): a missing plan.md is evidence that
    # positive plan-completion prose is a false claim — even when other work
    # happened (e.g. only todo.md was written), a claimed plan.md still must be
    # corrected.
    missing_plan = (manifest or {}).get("plan_artifacts") or {}
    missing = (missing_plan.get("missing") or []) if isinstance(missing_plan, dict) else []
    if missing and not plan_claim_is_negative(text):
        return f"[Not implemented] {text}\n\n(Plan artifacts not written: {', '.join(missing)}.)"
    if not text or _did_work(manifest):
        return text
    if not _claim_contradicts_evidence(text):
        return text
    evidence = (
        f"No file was created or modified in this turn"
        f" (plan artifacts not written: {', '.join(missing)})."
        if missing
        else "No file was created or modified in this turn."
    )
    return f"[Not implemented] {text}\n\n({evidence})"


def _handoff_messages(collected_events: list[Event], response_text: str) -> list[Message]:
    """Flatten the typed event stream into Message objects for weak-model summarization."""
    msgs: list[Message] = []
    for ev in collected_events or []:
        if ev.kind == EventKind.MESSAGE and ev.data.get("text"):
            msgs.append(
                Message(
                    session_id=ev.session_id or "",
                    role="assistant",
                    content=str(ev.data["text"]),
                )
            )
        elif ev.kind == EventKind.TOOL_RESULT and ev.data.get("label"):
            digest = str(ev.data.get("digest") or ev.data.get("label"))
            msgs.append(Message(session_id=ev.session_id or "", role="tool", content=digest))
    if response_text:
        msgs.append(Message(session_id="", role="assistant", content=response_text))
    return msgs


class PromptExecutor:
    def __init__(
        self,
        config: AppSettings,
        provider: BaseProvider,
        tool_registry: ToolRegistry,
        session_repo: FileSessionRepository,
        message_repo: FileMessageRepository,
        skill_loader: SkillLoader,
        workspace_repo=None,
    ) -> None:
        self._config = config
        self._provider = provider
        self._tool_registry = tool_registry
        self._session_repo = session_repo
        self._message_repo = message_repo
        self._skill_loader = skill_loader
        self._workspace_repo = workspace_repo
        self._active_task: asyncio.Task | None = None
        self._context_manager = ContextManager(self._config)
        self._summary_scheduler = RunningSummaryScheduler(
            config, provider, session_repo, message_repo
        )
        from server.agents.compaction_service import CompactionService

        self._compaction_service = CompactionService(
            config,
            provider,
            context_manager=self._context_manager,
            session_repo=session_repo,
            message_repo=message_repo,
        )
        self._specialist_registry = SpecialistRegistry.default()
        self._repo_intelligence_cache = RepositoryIntelligenceCache()

    def cancel_active(self) -> None:
        if self._active_task and (not self._active_task.done()):
            self._active_task.cancel()

    def run(
        self,
        session_id: str,
        content: str,
        mode: str = BUILD_MODE,
        handlers: MethodHandlers | None = None,
        manager=None,
        model_override: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        attachments: list[dict] | None = None,
    ) -> None:
        import functools

        self._active_task = asyncio.create_task(
            self._execute(
                session_id,
                content,
                mode,
                handlers,
                manager,
                model_override,
                temperature,
                max_tokens,
                attachments,
            )
        )
        self._active_task.add_done_callback(functools.partial(self._on_task_done, session_id))

    def _on_task_done(self, session_id: str, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error(
                "BACKGROUND TASK FAILED session=%s error=%s", session_id, exc, exc_info=exc
            )

    async def _inject_attachments(
        self,
        content: str,
        attachments: list[dict],
        session_id: str,
        manager,
        collected_events: list[Event],
    ) -> str:
        blocks: list[str] = []
        total = 0
        for att in attachments:
            path = att.get("path", "") if isinstance(att, dict) else ""
            if not path:
                continue
            inline = att.get("content") if isinstance(att, dict) else None
            if isinstance(inline, str) and inline.strip():
                text, error = (inline, None)
            else:
                read_text, error = await read_attachment(path, self._config.workspace_root)
                text = read_text if isinstance(read_text, str) else ""
            if error:
                warning = r.warning(f"Skipped attachment '{path}': {error}", session_id)
                collected_events.append(warning)
                if manager:
                    await manager.send_event(session_id, warning)
                continue
            total += len(text.encode("utf-8"))
            if total > ATTACHMENT_MAX_TOTAL:
                warning = r.warning(
                    f"Skipped attachment '{path}': total attachment size exceeds {ATTACHMENT_MAX_TOTAL} bytes",
                    session_id,
                )
                collected_events.append(warning)
                if manager:
                    await manager.send_event(session_id, warning)
                continue
            blocks.append(f'<attachment path="{path}">\n{text}\n</attachment>')
        if not blocks:
            return content
        injected = "\n\n".join(blocks) + "\n\n" + content
        logger.info(
            "Injected %d attachment block(s) into prompt for session %s (content %d -> %d chars)",
            len(blocks),
            session_id,
            len(content),
            len(injected),
        )
        return injected

    async def _load_plan_context(self, session_id: str, mode: str) -> tuple[str, bool, str | None]:
        plan_context = ""
        plan_approved = False
        if mode == BUILD_MODE:
            try:
                session = await self._session_repo.get(session_id)
                if session and session.plan_output:
                    plan_context = session.plan_output
                    plan_approved = session.plan_approved_at is not None
                    logger.info(
                        "Plan context loaded: %d chars for build session %s (approved=%s)",
                        len(plan_context),
                        session_id,
                        plan_approved,
                    )
            except Exception:
                logger.warning("Failed to load plan context for session %s", session_id)
        plan_model_override: str | None = None
        if mode == PLAN_MODE and self._config.plan_model:
            plan_model_override = self._config.plan_model
            logger.info("Plan mode model override: %s", plan_model_override)
        return plan_context, plan_approved, plan_model_override

    async def _maybe_emit_plan_ready(
        self,
        session_id: str,
        mode: str,
        content: str,
        plan_context: str,
        plan_approved: bool,
        manager,
        collected_events: list[Event],
    ) -> int:
        if (
            mode == BUILD_MODE
            and plan_context
            and (not plan_approved)
            and (not self._config.auto_approve_plan)
            and (not (content and content.strip()))
        ):
            logger.info("Plan not yet approved — emitting PLAN_READY for session %s", session_id)
            plan_ready_event = Event(
                kind=EventKind.PLAN_READY,
                data={"plan": plan_context, "session_id": session_id},
                session_id=session_id,
            )
            if manager:
                await manager.send_event(session_id, plan_ready_event)
            collected_events.append(plan_ready_event)
            logger.info("Plan not approved — waiting for approval before build")
            warning_event = r.warning(
                "Plan is pending approval. Approve in the UI or use plan.approve to continue.",
                session_id,
            )
            if manager:
                await manager.send_event(session_id, warning_event)
            collected_events.append(warning_event)
            return 1
        return 0

    async def _persist_plan_output(self, session_id: str, response_text: str) -> None:
        try:
            session = await self._session_repo.get(session_id)
            if session:
                session.plan_output = response_text
                if self._config.auto_approve_plan:
                    session.plan_approved_at = datetime.now()
                else:
                    session.plan_approved_at = None
                session.state = SessionState.SUMMARIZED
                await self._session_repo.update(session)
                logger.info(
                    "Plan output saved to session %s: %d chars (auto_approve=%s)",
                    session_id,
                    len(response_text),
                    self._config.auto_approve_plan,
                )
        except Exception:
            logger.warning("Failed to save plan output for session %s", session_id)

    async def _persist_run_state(
        self,
        session_id: str,
        objective: str,
        mode: str,
        collected_events: list[Event],
        ts: float,
    ) -> dict | None:
        """Fold this turn's executed events into the session's structured run state.

        The run state is evidence-derived (executed tool events + turn manifest),
        never inferred from model prose. It is stored under the additive
        ``session.metadata["run_state"]`` key, so older sessions without it
        initialize safely (QA-4). Returns the persisted snapshot (or None when
        the session is absent), so callers can emit it to the frontend.
        """
        try:
            current = await self._session_repo.get_metadata(session_id)
            if current is None:
                return None
            previous = from_dict((current or {}).get("run_state"))
            state = merge_run_state(previous, ts=ts)
            state.objective = objective or state.objective
            state.mode = mode
            for ev in collected_events or []:
                update_from_event(state, ev.kind, ev.data or {}, ev.timestamp)
            # Session-scoped todos are authoritative; export them into run_state
            # so plan artifacts (todo.md) render FROM this structured state.
            try:
                from server.agents.todo_state import get_todo_state

                state.todo = get_todo_state(session_id).snapshot()
            except Exception:
                state.todo = list(state.todo)
            workspace_root = None
            if hasattr(self._session_repo, "get_workspace_root"):
                workspace_root = await self._session_repo.get_workspace_root(session_id)
            if workspace_root is None:
                session_row = await self._session_repo.get(session_id)
                workspace_root = session_row.workspace_root if session_row else None
            self._render_todo_artifact(workspace_root, session_id, state.todo)
            snapshot = state.to_dict()
            # Metadata-only targeted write: never a whole-record update, so a
            # concurrent token-count/model writer cannot be clobbered here.
            await self._session_repo.merge_metadata(session_id, {"run_state": snapshot})
            # Unique executed calls (P6.5): tool_history holds one entry per
            # call AND result event, so its raw length double-counts.
            executed_calls = sum(
                1 for step in state.tool_history if step.get("kind") == "tool_call"
            )
            logger.info(
                "Persisted run state for session %s: status=%s tool_calls=%d",
                session_id,
                state.status,
                executed_calls,
            )
            return snapshot
        except Exception:
            logger.exception("Failed to persist run state for session %s", session_id)
            return None

    def _render_todo_artifact(self, workspace_root: str | None, session_id: str, todos) -> None:
        """Write ``todo.md`` from the structured todo snapshot (QA-5.8).

        The artifact is only rendered when structured todos exist so a
        model-authored ``todo.md`` is never clobbered by an empty board.
        """
        if not todos:
            return
        try:
            from server.agents.todo_state import render_todo_markdown

            root = Path(workspace_root or self._config.workspace_root)
            root.mkdir(parents=True, exist_ok=True)
            (root / "todo.md").write_text(render_todo_markdown(todos), encoding="utf-8")
            logger.info(
                "Rendered todo.md artifact for session %s (%d todos)",
                session_id,
                len(todos),
            )
        except Exception:
            logger.warning("Failed to render todo.md artifact for session %s", session_id)

    async def _persist_assistant_message(
        self,
        session_id: str,
        response_text: str,
        collected_events: list[Event],
        terminal_status: str = TERMINAL_STATUS_COMPLETED,
    ) -> None:
        try:
            events = list(collected_events or [])
            if not (events or response_text.strip()):
                logger.info("Skipping empty assistant message (no events or text)")
                return
            manifest = _turn_manifest_from_events(events)
            worked = _did_work(manifest)
            body = response_text
            if not worked:
                # The manifest is authoritative: never persist prose that asserts
                # files were created/modified when the execution record proves none were.
                body = _rewrite_false_completion_claim(response_text, manifest)
            handoff = _build_crafted_handoff(manifest, body)
            if worked and body.strip() and len(body) > _HANDOFF_SUMMARY_CHARS:
                summarized = await self._summarize_handoff(session_id, events, body)
                if summarized:
                    handoff = _build_crafted_handoff(manifest, summarized)
            if not handoff:
                # Never persist a placeholder when real work happened. The
                # placeholder reflects the actual terminal condition
                # (AGENT_RELIABILITY_PLAN P1.4): "[Cancelled by user]" is only
                # ever produced by a real cancellation, never assumed.
                if terminal_status == TERMINAL_STATUS_CANCELLED:
                    handoff = HANDOFF_PLACEHOLDER_CANCELLED
                elif terminal_status == TERMINAL_STATUS_ERROR:
                    handoff = HANDOFF_PLACEHOLDER_ERROR
                else:
                    handoff = HANDOFF_PLACEHOLDER_NO_SUMMARY
            if len(handoff) > _HANDOFF_MAX_CHARS:
                handoff = handoff[:_HANDOFF_MAX_CHARS].rstrip() + "…"
            text_content = handoff.strip()
            if not text_content:
                logger.info("Skipping blank assistant message for session %s", session_id)
                return
            from server.toolkit.executor import redact_pii

            text_content = redact_pii(text_content)
            assistant_msg = Message(
                session_id=session_id,
                role="assistant",
                content=text_content,
                events=events,
            )
            await self._message_repo.create(assistant_msg)
            logger.info(
                "Assistant message persisted: %d events, %d chars, worked=%s",
                len(events),
                len(text_content),
                worked,
            )
        except Exception:
            logger.exception("Failed to persist assistant message for session %s", session_id)

    async def _summarize_handoff(
        self, session_id: str, collected_events: list[Event], response_text: str
    ) -> str | None:
        """Weak-model summarization fallback for long/no-text turns (never blocking success)."""
        try:
            from server.agents.summarizer import ConversationSummarizer

            summarizer = ConversationSummarizer(self._config, self._provider)
            model = str(getattr(self._provider, "model", "") or "")
            return await summarizer.summarize(
                _handoff_messages(collected_events, response_text), model, session_id
            )
        except Exception as e:
            logger.warning("Hand-off summarization failed: %s", e)
            return None

    async def _execute(
        self,
        session_id: str,
        content: str,
        mode: str,
        handlers: MethodHandlers | None,
        manager,
        model_override: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        attachments: list[dict] | None = None,
    ) -> None:
        logger.info("=" * 60)
        logger.info("_execute START session=%s mode=%s prompt=%r", session_id, mode, content)
        collected_events: list[Event] = []
        response_text = ""
        event_count = 0
        token_usage_recorded = False
        _step_count = 0
        # C-F02: terminal events (SUCCESS/ERROR) are held back until the
        # end-of-run SESSION_SUMMARIZED snapshot has been persisted and sent.
        # The TUI client finalizes and unsubscribes on the first terminal
        # event, so forwarding SUCCESS/ERROR before the summary means the
        # summary is silently dropped (and never replayed, since it was not
        # part of the persisted message either).
        _pending_terminal: list[Event] = []
        _original_model: str | None = None
        _original_temperature: float | None = None
        _original_max_tokens: int | None = None
        # Bound before any early return (plan-ready / CrewmateLoop handoff):
        # the finally block reads these, and an UnboundLocalError there would
        # skip assistant-message persistence and terminal-event delivery.
        agent: RecoverableAgentLoop | None = None
        db_session = None
        summary_at_start: str | None = None
        # What actually ended the turn (AGENT_RELIABILITY_PLAN P1.4): the
        # persistence placeholder must reflect the real terminal condition,
        # never assume a user cancellation.
        _terminal_status = TERMINAL_STATUS_COMPLETED
        try:
            history = await self._message_repo.get_by_session(session_id)
            logger.info("History loaded: %d messages for session %s", len(history), session_id)
            plan_context, plan_approved, plan_model_override = await self._load_plan_context(
                session_id, mode
            )
            if await self._maybe_emit_plan_ready(
                session_id,
                mode,
                content,
                plan_context,
                plan_approved,
                manager,
                collected_events,
            ):
                _step_count += 1
                return
            _original_model = getattr(self._provider, "model", None)
            _original_temperature = getattr(self._provider, "temperature", None)
            _original_max_tokens = getattr(self._provider, "max_tokens", None)
            completed_ok = False
            effective_model = model_override or plan_model_override
            if effective_model and effective_model != _original_model:
                logger.info("Per-prompt model override: %s -> %s", _original_model, effective_model)
                self._provider.model = effective_model
            if temperature is not None:
                self._provider.temperature = temperature
            if max_tokens is not None:
                self._provider.max_tokens = max_tokens
            if attachments:
                content = await self._inject_attachments(
                    content, attachments, session_id, manager, collected_events
                )

            mode_config = AGENT_MODES.get(mode)
            crewmate_handoff = (
                mode == BUILD_MODE
                and plan_context
                and plan_approved
                and mode_config
                and mode_config.crewmate
            )

            # Captain delegation route: capability-driven dispatch to a
            # specialist agent. Never hijacks plan mode, never competes with
            # the plan->build CrewmateLoop handoff (trigger conditions are
            # disjoint); non-matching prompts fall through to the normal loop.
            # Governance (WP5 D3, revised after live incident): 'tool' (the
            # default) means ONLY the mid-turn explore tool delegates — the
            # pre-loop route requires explicit 'proactive'. Evidence: the
            # router captured research prompts and ran them on the legacy path
            # (fixed 120s timeout, no budgets), starving the better tool path.
            if (
                mode != PLAN_MODE
                and not crewmate_handoff
                and self._config.explore_delegation == EXPLORE_DELEGATION_PROACTIVE
            ):
                routed_definition = self._specialist_registry.route(content)
                if routed_definition is not None:
                    logger.info(
                        "Captain delegating session=%s capability-route -> %s",
                        session_id,
                        routed_definition.id,
                    )
                    orchestrator = CaptainOrchestrator(
                        self._config,
                        self._provider,
                        self._tool_registry,
                        session_repo=self._session_repo,
                        message_repo=self._message_repo,
                        compaction_service=self._compaction_service,
                        cache=self._repo_intelligence_cache,
                    )
                    async for event in orchestrator.investigate(
                        content, routed_definition, session_id, history=history
                    ):
                        event_count += 1
                        collected_events.append(event)
                        if manager:
                            await manager.send_event(session_id, event)
                    if orchestrator.last_result is not None:
                        response_text = orchestrator.last_result.summary
                    logger.info(
                        "Delegation complete session=%s result=%s",
                        session_id,
                        orchestrator.last_result.status if orchestrator.last_result else "none",
                    )
                    return

            if crewmate_handoff:
                logger.info("Spawning CrewmateLoop for session %s (plan→build handoff)", session_id)
                crewmate_loop = CrewmateLoop(
                    self._config,
                    self._provider,
                    self._tool_registry,
                    compaction_service=self._compaction_service,
                )
                async for event in crewmate_loop.run(
                    session_id=session_id,
                    plan_output=plan_context,
                    user_prompt=content,
                    session_repo=self._session_repo,
                    message_repo=self._message_repo,
                ):
                    event_count += 1
                    collected_events.append(event)
                    if manager:
                        await manager.send_event(session_id, event)
                logger.info(
                    "CrewmateLoop completed for session %s: %d events", session_id, event_count
                )
                return
            context_manager = self._context_manager
            agent = RecoverableAgentLoop(
                self._config,
                self._provider,
                context_manager,
                self._tool_registry,
                self._compaction_service,
            )
            db_session = await self._session_repo.get(session_id)
            summary_at_start = (db_session.metadata or {}).get("summary") if db_session else None
            if db_session and db_session.metadata and db_session.metadata.get("summary"):
                agent.set_summary(db_session.metadata["summary"])
                logger.info(
                    "Loaded persisted session summary (%d chars) for %s",
                    len(db_session.metadata["summary"]),
                    session_id,
                )
            skills_section = self._skill_loader.get_skill_prompt()
            logger.info("Agent initialized, skills loaded=%d chars", len(skills_section))
            async for event in agent.process_prompt(
                content,
                session_id,
                history,
                mode,
                skills_section=skills_section,
                plan_context=plan_context,
                model_override=None,
                repo_map="" if mode == PLAN_MODE else None,
            ):
                event_count += 1
                collected_events.append(event)
                if event.kind == EventKind.MESSAGE:
                    if not event.data.get("partial"):
                        if event.data.get("iteration"):
                            _step_count += 1
                        logger.info("  [ASSISTANT MESSAGE]: %s", event.data.get("text", ""))
                elif event.kind == EventKind.THINKING:
                    logger.info("  [THINKING]: %s", event.data.get("text", ""))
                elif event.kind == EventKind.TOOL_CALL:
                    from server.toolkit.executor import redact_tool_params

                    logger.info(
                        " [TOOL CALL]: tool=%s params=%s",
                        event.data.get("tool", ""),
                        redact_tool_params(event.data.get("params", {}) or {}),
                    )
                elif event.kind == EventKind.TOOL_RESULT:
                    out = str(event.data.get("output", ""))
                    logger.info(
                        " [TOOL RESULT]: tool=%s success=%s output_len=%d error=%s",
                        event.data.get("tool", ""),
                        event.data.get("success"),
                        len(out),
                        event.data.get("error", ""),
                    )
                elif event.kind == EventKind.ERROR:
                    logger.info(
                        " ERROR: message=%s code=%s recoverable=%s",
                        event.data.get("message", ""),
                        event.data.get("code"),
                        event.data.get("recoverable"),
                    )
                elif event.kind == EventKind.SUCCESS:
                    logger.info(
                        " SUCCESS: iterations=%s token_info=%s",
                        event.data.get("iterations"),
                        event.data.get("tokenInfo"),
                    )
                    if event.data.get("tokenInfo"):
                        try:
                            ti = event.data["tokenInfo"]
                            token_repo = FileTokenUsageRepository(self._session_repo.home)
                            provider_name = getattr(self._provider, "name", "unknown")
                            model_name = getattr(self._provider, "model", "unknown")
                            # QA-10: `used` is composed-context OCCUPANCY (gauge
                            # input); runTotal/runPrompt/runCompletion are the
                            # provider-billed run usage (spend). They are
                            # persisted separately and never mixed.
                            used = ti.get("used", 0)
                            run_total = ti.get("runTotal", 0) or used
                            prompt_t = ti.get("prompt_tokens", ti.get("runPrompt", run_total))
                            completion_t = ti.get("completion_tokens", ti.get("runCompletion", 0))
                            cache_read_t = ti.get("cached_tokens", 0)
                            cache_creation_t = ti.get("cache_creation_tokens", 0)
                            ctx_window = ti.get("total", DEFAULT_CONTEXT_WINDOW)
                            estimated = bool(ti.get("estimated", False))
                            if _step_count > 0:
                                for s in range(1, _step_count + 1):
                                    await token_repo.record(
                                        session_id=session_id,
                                        provider=provider_name,
                                        model=model_name,
                                        total_tokens=run_total // _step_count,
                                        context_window=ctx_window,
                                        prompt_tokens=prompt_t // _step_count,
                                        completion_tokens=completion_t // _step_count,
                                        input_tokens=prompt_t // _step_count,
                                        output_tokens=completion_t // _step_count,
                                        cache_read_tokens=cache_read_t // _step_count,
                                        cache_creation_tokens=cache_creation_t // _step_count,
                                        step_index=s,
                                        estimated=estimated,
                                        # Occupancy is a composed snapshot: only
                                        # the final step of the turn carries it.
                                        context_occupancy=used if s == _step_count else 0,
                                    )
                            elif not token_usage_recorded:
                                await token_repo.record(
                                    session_id=session_id,
                                    provider=provider_name,
                                    model=model_name,
                                    total_tokens=run_total,
                                    context_window=ctx_window,
                                    prompt_tokens=prompt_t,
                                    completion_tokens=completion_t,
                                    input_tokens=prompt_t,
                                    output_tokens=completion_t,
                                    cache_read_tokens=cache_read_t,
                                    cache_creation_tokens=cache_creation_t,
                                    estimated=estimated,
                                    context_occupancy=used,
                                )
                            token_usage_recorded = True
                            logger.info(
                                "Token usage recorded: provider=%s model=%s tokens=%d/%d cache_read=%d cache_creation=%d",
                                provider_name,
                                model_name,
                                used,
                                ctx_window,
                                cache_read_t,
                                cache_creation_t,
                            )
                            try:
                                await self._session_repo.add_tokens(session_id, used)
                            except Exception as e:
                                logger.warning("Failed to update session token count: %s", e)
                        except Exception as e:
                            logger.warning("Failed to record token usage: %s", e)
                elif event.kind == EventKind.WARNING:
                    msg = event.data.get("message", "")
                    logger.info("  WARNING: %s", msg[:200])
                else:
                    logger.info("  OTHER: %s", str(event.data)[:200])
                if manager:
                    if event.kind in (EventKind.SUCCESS, EventKind.ERROR):
                        _pending_terminal.append(event)
                    else:
                        await manager.send_event(session_id, event)
                if event.kind == EventKind.MESSAGE and (not event.data.get("partial")):
                    response_text += event.data.get("text", "")
            completed_ok = True
            if mode == PLAN_MODE and response_text:
                await self._persist_plan_output(session_id, response_text)
            logger.info("=" * 60)
            logger.info(
                "_execute COMPLETE: events=%d response_text_len=%d", event_count, len(response_text)
            )
        except asyncio.CancelledError:
            logger.info("PromptExecutor._execute CANCELLED for session %s", session_id)
            _terminal_status = TERMINAL_STATUS_CANCELLED
            cancel_event = r.warning("Generation interrupted by user (ESC)", session_id)
            if manager:
                await manager.send_event(session_id, cancel_event)
            collected_events.append(cancel_event)
            raise
        except Exception as e:
            logger.exception(
                "PromptExecutor._execute FAILED for session %s after %d events",
                session_id,
                event_count,
            )
            _terminal_status = TERMINAL_STATUS_ERROR
            error_event = Event(
                kind=EventKind.ERROR, data={"message": str(e)}, session_id=session_id
            )
            _pending_terminal.append(error_event)
            collected_events.append(error_event)
        finally:
            if _original_model is not None:
                self._provider.model = _original_model
            if _original_temperature is not None:
                self._provider.temperature = _original_temperature
            if _original_max_tokens is not None:
                self._provider.max_tokens = _original_max_tokens
            if (
                agent is not None
                and agent.summary
                and (db_session is None or summary_at_start != agent.summary)
            ):
                try:
                    # Only apply the in-memory summary if no newer writer (manual
                    # compaction or a background running summary) replaced it
                    # while this turn was in flight: a stale result must never
                    # overwrite newer session state. Metadata-only targeted
                    # write — never a stale whole-record update.
                    current = await self._session_repo.get_metadata(session_id)
                    if current is None:
                        logger.info(
                            "Skipped summary persist for %s: session no longer exists",
                            session_id,
                        )
                    elif (current or {}).get("summary") in (summary_at_start, None, ""):
                        await self._session_repo.merge_metadata(
                            session_id, {"summary": agent.summary}
                        )
                        logger.info(
                            "Persisted updated session summary (%d chars) for %s",
                            len(agent.summary),
                            session_id,
                        )
                    else:
                        logger.info(
                            "Skipped summary persist for %s: newer summary exists",
                            session_id,
                        )
                except Exception as e:
                    logger.warning("Failed to persist session summary: %s", e)
            # C-F02 ordering: compute the end-of-run snapshot BEFORE persisting
            # the assistant message so SESSION_SUMMARIZED is part of the
            # persisted event trail (replayable on resume), then deliver it to
            # the live client BEFORE any terminal event.
            persisted_state = None
            try:
                persisted_state = await self._persist_run_state(
                    session_id, content, mode, collected_events, time.time()
                )
            except Exception:
                logger.debug("Failed to persist run state for %s", session_id)
            summarized_event: Event | None = None
            if persisted_state and persisted_state.get("final"):
                # The authoritative end-of-run summary; FinalSummaryCard renders
                # FROM this snapshot, never from prose.
                summary = (getattr(agent, "summary", None) or "").strip() or response_text.strip()
                summarized_event = Event(
                    kind=EventKind.SESSION_SUMMARIZED,
                    session_id=session_id,
                    data={
                        "summary": summary,
                        "findings": list(persisted_state.get("findings") or []),
                        "run_state": persisted_state,
                    },
                )
                collected_events.append(summarized_event)
            await self._persist_assistant_message(
                session_id, response_text, collected_events, terminal_status=_terminal_status
            )
            if manager and summarized_event is not None:
                await manager.send_event(session_id, summarized_event)
            if manager:
                for terminal in _pending_terminal:
                    await manager.send_event(session_id, terminal)
                _pending_terminal.clear()
            if self._workspace_repo:
                try:
                    from server.agents.session_workspace import flush_to_db

                    await flush_to_db(session_id, self._workspace_repo)
                except Exception:
                    logger.debug("Failed to flush workspace to DB for %s", session_id)
            if completed_ok:
                self._summary_scheduler.schedule(session_id)
