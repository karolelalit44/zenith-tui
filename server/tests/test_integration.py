from pathlib import Path

import pytest

from server.agents.context import ContextManager
from server.agents.loop import AgentLoop
from server.agents.recovery import RecoverableAgentLoop
from server.api.shutdown import GracefulShutdown
from server.config.providers import ProviderConfig
from server.config.settings import AppSettings
from server.domain.events import Event, EventKind
from server.domain.message import Message
from server.domain.session import Session
from server.providers.base import BaseProvider
from server.providers.registry import ProviderRegistry
from server.sessions.export import SessionExporter
from server.skills.loader import SkillLoader
from server.toolkit import create_default_registry
from server.workspace.repo_map import RepoMap


class EchoProvider(BaseProvider):
    def __init__(self, respond_with_tool: bool = False):
        super().__init__("test", "test-model")
        self.respond_with_tool = respond_with_tool
        self.call_count = 0

    async def complete(self, messages: list[dict], tools=None) -> str:
        self.call_count += 1
        user_msg = messages[-1]["content"] if messages else ""
        if self.respond_with_tool and self.call_count == 1:
            return '```tool\n{"tool": "file_read", "params": {"path": "test.txt"}}\n```'
        return f"Echo: {user_msg}"

    async def stream(
        self, messages: list[dict], tools=None, tool_choice=None, response_format=None
    ):
        response = await self.complete(messages)
        for char in response:
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["test-model"]


@pytest.fixture
def test_config(temp_dir):
    return AppSettings(
        providers={"test": ProviderConfig(model="test-model", is_active=True)},
        active_provider="test",
        home_dir=str(temp_dir),
        workspace_root=str(temp_dir),
    )


@pytest.fixture
def test_home(test_config):
    from server.storage import StorageHome, ensure_materialized

    h = StorageHome(test_config.home_dir)
    ensure_materialized(h)
    return h


@pytest.fixture
def test_registry():
    registry = ProviderRegistry()
    registry.register("test", EchoProvider())
    return registry


class TestAgentWorkflow:
    @pytest.mark.asyncio
    async def test_simple_prompt(self, test_config):
        provider = EchoProvider()
        agent = AgentLoop(test_config, provider)
        events = []
        async for event in agent.process_prompt("Hello", "s1", [], "build"):
            events.append(event)
        assert events[0].kind == EventKind.MESSAGE
        assert any(e.kind == EventKind.MESSAGE for e in events)
        assert events[-1].kind == EventKind.SUCCESS

    @pytest.mark.asyncio
    async def test_tool_call_flow(self, test_config):
        provider = EchoProvider(respond_with_tool=True)
        tool_registry = create_default_registry()
        agent = AgentLoop(test_config, provider, tool_registry=tool_registry)
        events = []
        async for event in agent.process_prompt("Read a file", "s1", [], "build"):
            events.append(event)
        kinds = [e.kind for e in events]
        assert EventKind.TOOL_CALL in kinds or EventKind.SUCCESS in kinds

    @pytest.mark.asyncio
    async def test_plan_mode_blocks_write_tools(self, test_config):
        provider = EchoProvider()
        tool_registry = create_default_registry()
        AgentLoop(test_config, provider, tool_registry=tool_registry)
        result = await tool_registry.execute(
            "file_write", {"path": "x", "content": "y"}, ".", mode="plan"
        )
        assert not result.success
        assert "only allows writing plan.md or todo.md" in result.error

    class _PostCompletionProvider(BaseProvider):
        def __init__(self):
            super().__init__("postcomp", "postcomp-model")
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            if self.call_count == 1:
                return (
                    "Done. The file has been created successfully.\n"
                    '```tool\n{"tool": "file_write", "params": {"path": "out.txt", '
                    '"content": "hello"}}\n```'
                )
            if self.call_count == 2:
                return (
                    '```tool\n{"tool": "file_write", "params": {"path": "out2.txt", '
                    '"content": "hello again"}}\n```'
                )
            return "All done."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self) -> bool:
            return True

        async def list_models(self) -> list[str]:
            return ["postcomp-model"]

    @pytest.mark.asyncio
    async def test_new_calls_after_completion_still_execute(self, test_config):
        """Event-driven semantics: a phrase like 'Done' does not gate behavior. A
        genuinely new tool call after that phrase still executes; only identical
        repeats are skipped (handled by the stall guard)."""
        root = Path(test_config.workspace_root)
        agent = AgentLoop(
            test_config,
            self._PostCompletionProvider(),
            tool_registry=create_default_registry(),
        )
        events = []
        async for event in agent.process_prompt("Create a file and finish", "s1", [], "build"):
            events.append(event)
        # The second call targets a NEW path, so it is genuinely new work and is
        # honored even though it follows the 'Done' phrase.
        assert (root / "out.txt").read_text(encoding="utf-8") == "hello"
        assert (root / "out2.txt").read_text(encoding="utf-8") == "hello again"
        assert events[-1].kind == EventKind.SUCCESS
        assert not any(e.kind == EventKind.ERROR for e in events)

    class _SamePathRewriteProvider(BaseProvider):
        def __init__(self):
            super().__init__("rewrite", "rewrite-model")
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            if self.call_count == 1:
                return (
                    '```tool\n{"tool": "file_write", "params": {"path": "a.txt", '
                    '"content": "v1"}}\n```'
                )
            if self.call_count == 2:
                return (
                    '```tool\n{"tool": "file_write", "params": {"path": "a.txt", '
                    '"content": "v2"}}\n'
                    '{"tool": "file_write", "params": {"path": "b.txt", "content": "b"}}\n```'
                )
            return "Done."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self) -> bool:
            return True

        async def list_models(self) -> list[str]:
            return ["rewrite-model"]

    @pytest.mark.asyncio
    async def test_same_path_rewrite_is_blocked(self, test_config):
        """One-write-per-path-per-turn: a second file_write to a path already
        written this turn is blocked even with different content, while other
        new work in the same response still executes."""
        root = Path(test_config.workspace_root)
        agent = AgentLoop(
            test_config,
            self._SamePathRewriteProvider(),
            tool_registry=create_default_registry(),
        )
        events = []
        async for event in agent.process_prompt("Write the files", "s1", [], "build"):
            events.append(event)
        assert (root / "a.txt").read_text(encoding="utf-8") == "v1", "first write must win"
        assert (root / "b.txt").read_text(encoding="utf-8") == "b", "other new work must run"
        warnings = [e for e in events if e.kind == EventKind.WARNING]
        assert any("File rewrite blocked" in (e.data.get("message") or "") for e in warnings)
        assert events[-1].kind == EventKind.SUCCESS
        assert not any(e.kind == EventKind.ERROR for e in events)


class TestMultiEditEndToEnd:
    class _MultiEditProvider(BaseProvider):
        def __init__(self):
            super().__init__("multiedit", "multiedit-model")
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            if self.call_count == 1:
                return '```tool\n{"tool": "file_write", "params": {"path": "src.txt", "content": "alpha\\nbeta\\ngamma"}}\n```'
            if self.call_count == 2:
                return (
                    '```tool\n{"tool": "multi_edit", "params": {"filepath": "src.txt", '
                    '"edits": [{"old_content": "alpha", "new_content": "alpha-one"}, '
                    '{"old_content": "gamma", "new_content": "gamma-three"}]}}\n```'
                )
            return "Done."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self):
            return True

        async def list_models(self):
            return ["multiedit-model"]

    @pytest.mark.asyncio
    async def test_multi_edit_executes_through_parser(self, test_config):
        root = Path(test_config.workspace_root)
        agent = AgentLoop(
            test_config,
            self._MultiEditProvider(),
            tool_registry=create_default_registry(),
        )
        events = []
        async for event in agent.process_prompt("Do the edits", "s1", [], "build"):
            events.append(event)
        assert (root / "src.txt").read_text(encoding="utf-8") == "alpha-one\nbeta\ngamma-three"
        results = [
            e
            for e in events
            if e.kind == EventKind.TOOL_RESULT and e.data.get("tool") == "multi_edit"
        ]
        assert len(results) == 1, "multi_edit must execute and succeed"
        assert results[0].data.get("success") is True, results[0].data.get("error", "")
        assert events[-1].kind == EventKind.SUCCESS
        assert not any(e.kind == EventKind.ERROR for e in events)


class TestAutoApprovalGates:
    class _WriteProvider(BaseProvider):
        def __init__(self):
            super().__init__("write", "write-model")
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            if self.call_count == 1:
                return '```tool\n{"tool": "file_write", "params": {"path": "out.txt", "content": "new content"}}\n```'
            return "Done"

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self) -> bool:
            return True

        async def list_models(self) -> list[str]:
            return ["write-model"]

    @pytest.mark.asyncio
    async def test_auto_overwrite_true_writes_existing_file(self, test_config):
        target = Path(test_config.workspace_root) / "out.txt"
        target.write_text("old", encoding="utf-8")
        agent = AgentLoop(
            test_config, self._WriteProvider(), tool_registry=create_default_registry()
        )
        events = []
        async for event in agent.process_prompt("Write file", "s1", [], "build"):
            events.append(event)
        assert target.read_text(encoding="utf-8") == "new content"
        results = [e for e in events if e.kind == EventKind.TOOL_RESULT]
        assert any(
            e.data.get("tool") == "file_write" and e.data.get("success") is True for e in results
        )
        assert events[-1].kind == EventKind.SUCCESS

    @pytest.mark.asyncio
    async def test_auto_overwrite_false_rejects_existing_file(self, test_config):
        # This test shares the "s1" session with other integration tests; clear the
        # durable write registry so a prior test's identical write to out.txt is not
        # mistaken for a replay and preempts the overwrite-denied gate under test.
        from server.agents.session_workspace import reset_session

        reset_session("s1")
        target = Path(test_config.workspace_root) / "out.txt"
        target.write_text("old", encoding="utf-8")
        test_config.auto_overwrite = False
        agent = AgentLoop(
            test_config, self._WriteProvider(), tool_registry=create_default_registry()
        )
        events = []
        async for event in agent.process_prompt("Write file", "s1", [], "build"):
            events.append(event)
        assert target.read_text(encoding="utf-8") == "old"
        warnings = [e for e in events if e.kind == EventKind.WARNING]
        overwrite_msgs = [
            e.data.get("message") or ""
            for e in warnings
            if "overwrite denied" in (e.data.get("message") or "")
        ]
        assert overwrite_msgs, "expected an overwrite-denied warning"
        # GAP4: the denial must tell the model the remedy (overwrite=true).
        assert "overwrite=true" in overwrite_msgs[0]

    @pytest.mark.asyncio
    async def test_new_file_writes_without_gate(self, test_config):
        agent = AgentLoop(
            test_config, self._WriteProvider(), tool_registry=create_default_registry()
        )
        events = []
        async for event in agent.process_prompt("Write file", "s1", [], "build"):
            events.append(event)
        assert (Path(test_config.workspace_root) / "out.txt").exists()
        assert events[-1].kind == EventKind.SUCCESS

    class _FileDeleteProvider(BaseProvider):
        def __init__(self, attempts: int = 1):
            super().__init__("delete", "delete-model")
            self.call_count = 0
            self.attempts = attempts

        async def complete(self, messages, tools=None):
            self.call_count += 1
            if self.call_count <= self.attempts:
                return '```tool\n{"tool": "file_delete", "params": {"path": "out.txt"}}\n```'
            return "Done"

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self) -> bool:
            return True

        async def list_models(self) -> list[str]:
            return ["delete-model"]

    @pytest.mark.asyncio
    async def test_auto_risky_true_deletes_file(self, test_config):
        target = Path(test_config.workspace_root) / "out.txt"
        target.write_text("old", encoding="utf-8")
        agent = AgentLoop(
            test_config,
            self._FileDeleteProvider(1),
            tool_registry=create_default_registry(),
        )
        events = []
        async for event in agent.process_prompt("Delete file", "s1", [], "build"):
            events.append(event)
        assert not target.exists(), "auto_risky=true must allow the delete"
        results = [e for e in events if e.kind == EventKind.TOOL_RESULT]
        assert any(
            e.data.get("tool") == "file_delete" and e.data.get("success") is True for e in results
        )

    @pytest.mark.asyncio
    async def test_auto_risky_false_keeps_file(self, test_config):
        target = Path(test_config.workspace_root) / "out.txt"
        target.write_text("old", encoding="utf-8")
        test_config.auto_risky = False
        agent = AgentLoop(
            test_config,
            self._FileDeleteProvider(3),
            tool_registry=create_default_registry(),
        )
        events = []
        async for event in agent.process_prompt("Delete file", "s1", [], "build"):
            events.append(event)
        assert target.exists(), "auto_risky=false must keep the file"
        warnings = [e for e in events if e.kind == EventKind.WARNING]
        assert any("delete denied" in (e.data.get("message") or "") for e in warnings)


class TestRepeatedCallTermination:
    class _RepeatingWriteProvider(BaseProvider):
        def __init__(self):
            super().__init__("repeater", "repeater-model")
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            if self.call_count == 1:
                return '```tool\n{"tool": "file_write", "params": {"path": "out.txt", "content": "same"}}\n```'
            return (
                "The task is complete. I am repeating the exact same write call again.\n"
                '```tool\n{"tool": "file_write", "params": {"path": "out.txt", "content": "same"}}\n```'
            )

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self):
            return True

        async def list_models(self):
            return ["repeater-model"]

    @pytest.mark.asyncio
    async def test_repeated_identical_calls_end_turn_cleanly(self, test_config):
        target = Path(test_config.workspace_root) / "out.txt"
        agent = AgentLoop(
            test_config,
            self._RepeatingWriteProvider(),
            tool_registry=create_default_registry(),
        )
        events = []
        async for event in agent.process_prompt("Write the file and stop", "s1", [], "build"):
            events.append(event)
        results = [
            e
            for e in events
            if e.kind == EventKind.TOOL_RESULT and e.data.get("tool") == "file_write"
        ]
        assert len(results) == 1, "the repeated identical call must not execute again"
        assert target.read_text(encoding="utf-8") == "same"
        warnings = [e for e in events if e.kind == EventKind.WARNING]
        assert not any(
            "No new tool was executed this iteration" in (e.data.get("message") or "")
            for e in warnings
        ), "a final summary with a stray repeated call must be accepted as completion, not stalled"
        manifests = [e for e in events if e.kind == EventKind.TURN_MANIFEST]
        assert manifests, "a completed turn must emit a turn_manifest"
        final_manifest = manifests[-1].data
        assert final_manifest.get("completed") is True, "the turn must report completed"
        assert final_manifest.get("stalled") is False, "the turn must not be stalled"
        assert events[-1].kind == EventKind.SUCCESS
        assert not any(e.kind == EventKind.ERROR for e in events)

    class _SummaryRepeaterProvider(BaseProvider):
        """Creates a file, then repeats the write call alongside a final summary.
        Records how many times the executed result appears in each request so the
        test can assert it is never re-injected (duplicated)."""

        def __init__(self):
            super().__init__("sumrep", "sumrep-model")
            self.call_count = 0
            self.result_occurrences: list[int] = []

        async def complete(self, messages, tools=None):
            self.call_count += 1
            self.result_occurrences.append(
                sum(
                    1
                    for m in messages
                    if isinstance(m.get("content"), str)
                    and "[Tool: file_write | Status: SUCCESS]" in m["content"]
                    and "out.txt" in m["content"]
                )
            )
            if self.call_count == 1:
                return '```tool\n{"tool": "file_write", "params": {"path": "out.txt", "content": "same"}}\n```'
            return (
                "The task is complete. I am repeating the exact same write call again.\n"
                '```tool\n{"tool": "file_write", "params": {"path": "out.txt", "content": "same"}}\n```'
            )

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self):
            return True

        async def list_models(self):
            return ["sumrep-model"]

    @pytest.mark.asyncio
    async def test_summary_with_repeat_is_accepted_without_duplicate_result(self, test_config):
        """B1/B2/B3: a final summary accompanying a repeated call completes the turn
        with no extra API call, and the stored result is never re-injected."""
        provider = self._SummaryRepeaterProvider()
        agent = AgentLoop(
            test_config,
            provider,
            tool_registry=create_default_registry(),
        )
        events = []
        async for event in agent.process_prompt("Write the file and stop", "s1", [], "build"):
            events.append(event)
        assert provider.call_count == 2, "no extra API call after the summary + repeat"
        assert provider.result_occurrences == [0, 1], (
            "the executed result must appear exactly once in the repeat request, "
            "never duplicated by the replay path"
        )
        manifests = [e for e in events if e.kind == EventKind.TURN_MANIFEST]
        assert manifests, "a completed turn must emit a turn_manifest"
        assert manifests[-1].data.get("completed") is True
        assert manifests[-1].data.get("stalled") is False
        assert events[-1].kind == EventKind.SUCCESS

    class _MixedProvider(BaseProvider):
        def __init__(self):
            super().__init__("mixed", "mixed-model")
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            if self.call_count == 1:
                return '```tool\n{"tool": "file_write", "params": {"path": "a.txt", "content": "a"}}\n```'
            if self.call_count == 2:
                return (
                    '```tool\n{"tool": "file_write", "params": {"path": "a.txt", "content": "a"}}\n'
                    '{"tool": "file_write", "params": {"path": "b.txt", "content": "b"}}\n```'
                )
            return "Done."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self):
            return True

        async def list_models(self):
            return ["mixed-model"]

    @pytest.mark.asyncio
    async def test_mixed_repeat_and_new_call_still_executes(self, test_config):
        root = Path(test_config.workspace_root)
        agent = AgentLoop(
            test_config,
            self._MixedProvider(),
            tool_registry=create_default_registry(),
        )
        events = []
        async for event in agent.process_prompt("Do the writes", "s1", [], "build"):
            events.append(event)
        assert (root / "a.txt").exists()
        assert (root / "b.txt").exists()
        warnings = [e for e in events if e.kind == EventKind.WARNING]
        assert not any(
            "No new tool was executed this iteration" in (e.data.get("message") or "")
            for e in warnings
        ), "new work alongside a repeat must not be treated as a stall"
        assert events[-1].kind == EventKind.SUCCESS


class TestDiscoveryRepeatSkip:
    class _DiscoveryRepeatProvider(BaseProvider):
        def __init__(self):
            super().__init__("discovery-repeat", "discovery-repeat-model")
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            if self.call_count == 1:
                return '```tool\n{"tool": "discover_capabilities", "params": {}}\n```'
            if self.call_count == 2:
                return (
                    '```tool\n{"tool": "get_tool_definition", "params": {"tool_name": "file_write"}}\n'
                    '{"tool": "file_write", "params": {"path": "a.txt", "content": "a"}}\n```'
                )
            if self.call_count == 3:
                return (
                    '```tool\n{"tool": "get_tool_definition", "params": {"tool_name": "file_write"}}\n'
                    '{"tool": "file_write", "params": {"path": "b.txt", "content": "b"}}\n```'
                )
            if self.call_count == 4:
                return (
                    '```tool\n{"tool": "get_tool_definition", "params": {"tool_name": "file_write"}}\n'
                    '{"tool": "file_write", "params": {"path": "c.txt", "content": "c"}}\n```'
                )
            return "Done."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self):
            return True

        async def list_models(self):
            return ["discovery-repeat-model"]

    @pytest.mark.asyncio
    async def test_repeated_discovery_calls_are_skipped(self, test_config):
        root = Path(test_config.workspace_root)
        agent = AgentLoop(
            test_config,
            self._DiscoveryRepeatProvider(),
            tool_registry=create_default_registry(),
        )
        events = []
        async for event in agent.process_prompt("Write three files", "s1", [], "build"):
            events.append(event)
        for name in ("a.txt", "b.txt", "c.txt"):
            assert (root / name).exists(), f"{name} must have been written"
        assert events[-1].kind == EventKind.SUCCESS, "turn must end with SUCCESS"
        assert not any(e.kind == EventKind.ERROR for e in events)
        warnings = [e for e in events if e.kind == EventKind.WARNING]
        assert any(
            "already completed with identical params this turn" in (e.data.get("message") or "")
            for e in warnings
        )

    class _HallucinatedCallsProvider(BaseProvider):
        def __init__(self):
            super().__init__("hallucinated", "hallucinated-model")
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            if self.call_count == 1:
                return (
                    '```tool\n{"tool": "file_write", "params": {"path": "a.txt", "content": "a"}}\n'
                    '{"tool": "frobnicate", "params": {"level": 9}}\n```'
                )
            return "Done."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self):
            return True

        async def list_models(self):
            return ["hallucinated-model"]

    class _AllHallucinatedProvider(BaseProvider):
        def __init__(self):
            super().__init__("all-hallucinated", "all-hallucinated-model")
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            if self.call_count == 1:
                return '```tool\n{"tool": "frobnicate", "params": {"level": 9}}\n```'
            if self.call_count == 2:
                return '```tool\n{"tool": "file_write", "params": {"path": "b.txt", "content": "b"}}\n```'
            return "Done."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self):
            return True

        async def list_models(self):
            return ["all-hallucinated-model"]

    @pytest.mark.asyncio
    async def test_mixed_valid_and_hallucinated_calls_do_not_crash(self, test_config):
        root = Path(test_config.workspace_root)
        agent = AgentLoop(
            test_config,
            self._HallucinatedCallsProvider(),
            tool_registry=create_default_registry(),
        )
        events = []
        async for event in agent.process_prompt("Write the file", "s1", [], "build"):
            events.append(event)
        assert (root / "a.txt").exists(), "valid call must still execute"
        warnings = [e for e in events if e.kind == EventKind.WARNING]
        assert any("Hallucinated tools ignored" in (e.data.get("message") or "") for e in warnings)
        assert events[-1].kind == EventKind.SUCCESS
        assert not any(e.kind == EventKind.ERROR for e in events)

    @pytest.mark.asyncio
    async def test_all_hallucinated_calls_feed_back_and_continue(self, test_config):
        root = Path(test_config.workspace_root)
        agent = AgentLoop(
            test_config,
            self._AllHallucinatedProvider(),
            tool_registry=create_default_registry(),
        )
        events = []
        async for event in agent.process_prompt("Write the file", "s1", [], "build"):
            events.append(event)
        assert (root / "b.txt").exists(), "loop must recover after hallucinated-only turn"
        assert events[-1].kind == EventKind.SUCCESS
        assert not any(e.kind == EventKind.ERROR for e in events)

    class _FailedReplayProvider(BaseProvider):
        def __init__(self):
            super().__init__("failed-replay", "failed-replay-model")
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            if self.call_count == 1:
                return '```tool\n{"tool": "file_read", "params": {"path": "missing.txt"}}\n```'
            if self.call_count == 2:
                return (
                    '```tool\n{"tool": "file_read", "params": {"path": "missing.txt"}}\n'
                    '{"tool": "file_write", "params": {"path": "a.txt", "content": "a"}}\n```'
                )
            return "Done."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self):
            return True

        async def list_models(self):
            return ["failed-replay-model"]

    @pytest.mark.asyncio
    async def test_identical_failed_call_is_not_re_executed(self, test_config):
        root = Path(test_config.workspace_root)
        agent = AgentLoop(
            test_config,
            self._FailedReplayProvider(),
            tool_registry=create_default_registry(),
        )
        events = []
        async for event in agent.process_prompt("Read then write", "s1", [], "build"):
            events.append(event)
        read_execs = [
            e
            for e in events
            if e.kind == EventKind.TOOL_RESULT and e.data.get("tool") == "file_read"
        ]
        assert len(read_execs) == 1, "identical failed call must not re-execute"
        assert read_execs[0].data.get("success") is False, "first attempt must still run and fail"
        assert (root / "a.txt").exists(), "new call in same response must still execute"
        warnings = [e for e in events if e.kind == EventKind.WARNING]
        assert any(
            "file_read(path=missing.txt) [failed]" in (e.data.get("message") or "")
            for e in warnings
        )
        assert events[-1].kind == EventKind.SUCCESS
        assert not any(e.kind == EventKind.ERROR for e in events)

    class _ReplayWorkProvider(BaseProvider):
        def __init__(self):
            super().__init__("replay", "replay-model")
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            if self.call_count == 1:
                return '```tool\n{"tool": "bash", "params": {"command": "mkdir out -Force"}}\n```'
            if self.call_count == 2:
                return (
                    '```tool\n{"tool": "bash", "params": {"command": "mkdir out -Force"}}\n'
                    '{"tool": "file_write", "params": {"path": "out/a.txt", "content": "a"}}\n```'
                )
            return "Done."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self):
            return True

        async def list_models(self):
            return ["replay-model"]

    @pytest.mark.asyncio
    async def test_repeated_real_work_calls_are_not_re_executed(self, test_config):
        root = Path(test_config.workspace_root)
        agent = AgentLoop(
            test_config,
            self._ReplayWorkProvider(),
            tool_registry=create_default_registry(),
        )
        events = []
        async for event in agent.process_prompt("Run the steps", "s1", [], "build"):
            events.append(event)
        results = [
            e for e in events if e.kind == EventKind.TOOL_RESULT and e.data.get("tool") == "bash"
        ]
        assert len(results) == 1, "the replayed bash call must not execute again"
        assert (root / "out" / "a.txt").exists()
        assert events[-1].kind == EventKind.SUCCESS
        assert not any(e.kind == EventKind.ERROR for e in events)
        warnings = [e for e in events if e.kind == EventKind.WARNING]
        assert any(
            "already completed with identical params this turn" in (e.data.get("message") or "")
            for e in warnings
        )

    class _ReplayNoCompletionProvider(BaseProvider):
        def __init__(self):
            super().__init__("replay-nc", "replay-nc-model")
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            if self.call_count == 1:
                return '```tool\n{"tool": "bash", "params": {"command": "mkdir out -Force"}}\n```'
            if self.call_count == 2:
                return (
                    '```tool\n{"tool": "bash", "params": {"command": "mkdir out -Force"}}\n'
                    '{"tool": "bash", "params": {"command": "mkdir out -Force"}}\n```'
                )
            if self.call_count == 3:
                return '```tool\n{"tool": "file_write", "params": {"path": "out/a.txt", "content": "a"}}\n```'
            return "Done."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self):
            return True

        async def list_models(self):
            return ["replay-nc-model"]

    @pytest.mark.asyncio
    async def test_all_repeat_without_completion_continues(self, test_config):
        root = Path(test_config.workspace_root)
        agent = AgentLoop(
            test_config,
            self._ReplayNoCompletionProvider(),
            tool_registry=create_default_registry(),
        )
        events = []
        async for event in agent.process_prompt("Run the steps", "s1", [], "build"):
            events.append(event)
        results = [
            e for e in events if e.kind == EventKind.TOOL_RESULT and e.data.get("tool") == "bash"
        ]
        assert len(results) == 1, "the replayed bash calls must not execute again"
        assert (root / "out" / "a.txt").exists(), "new work after the replay must still run"
        assert events[-1].kind == EventKind.SUCCESS
        assert not any(e.kind == EventKind.ERROR for e in events)
        warnings = [e for e in events if e.kind == EventKind.WARNING]
        assert any(
            "No new tool was executed this iteration" in (e.data.get("message") or "")
            for e in warnings
        ), "repeated calls without completion must trigger the corrective stall nudge, not finalize"


class TestStallGuard:
    class _StallProvider(BaseProvider):
        def __init__(self):
            super().__init__("stall", "stall-model")
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            if self.call_count == 1:
                return '```tool\n{"tool": "file_write", "params": {"path": "a.txt", "content": "a"}}\n```'
            if self.call_count <= 4:
                return (
                    '```tool\n{"tool": "file_write", "params": {"path": "a.txt", "content": "a"}}\n'
                    '{"tool": "file_write", "params": {"path": "a.txt", "content": "a"}}\n```'
                )
            return "Done."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self):
            return True

        async def list_models(self):
            return ["stall-model"]

    @pytest.mark.asyncio
    async def test_repeated_no_new_work_finalizes_turn(self, test_config):
        root = Path(test_config.workspace_root)
        agent = AgentLoop(
            test_config,
            self._StallProvider(),
            tool_registry=create_default_registry(),
        )
        events = []
        async for event in agent.process_prompt("Do the write", "s1", [], "build"):
            events.append(event)
        results = [
            e
            for e in events
            if e.kind == EventKind.TOOL_RESULT and e.data.get("tool") == "file_write"
        ]
        assert len(results) == 1, "repeated write must not re-execute"
        assert (root / "a.txt").read_text(encoding="utf-8") == "a"
        warnings = [e for e in events if e.kind == EventKind.WARNING]
        assert any(
            "No new tool was executed this iteration" in (e.data.get("message") or "")
            for e in warnings
        ), "the stall nudge must list remaining tools"
        assert any(
            "No new tool work for several consecutive iterations" in (e.data.get("message") or "")
            for e in warnings
        ), "the turn must finalize after repeated stalls"
        assert events[-1].kind == EventKind.SUCCESS
        assert not any(e.kind == EventKind.ERROR for e in events)

    class _PathObsessionProvider(BaseProvider):
        """Keeps re-writing the same path with new content while interleaving other
        new files. Each iteration has new work, so the stall counter never fires;
        the path-stuck detector must finalize the turn instead."""

        def __init__(self):
            super().__init__("obsess", "obsess-model")
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            n = self.call_count
            if n == 1:
                return (
                    '```tool\n{"tool": "file_write", "params": {"path": "a.txt", '
                    '"content": "v1"}}\n```'
                )
            if n == 2:
                return (
                    '```tool\n{"tool": "file_write", "params": {"path": "a.txt", '
                    '"content": "v2"}}\n'
                    '{"tool": "file_write", "params": {"path": "b.txt", "content": "b"}}\n```'
                )
            if n == 3:
                return (
                    '```tool\n{"tool": "file_write", "params": {"path": "a.txt", '
                    '"content": "v3"}}\n'
                    '{"tool": "file_write", "params": {"path": "c.txt", "content": "c"}}\n```'
                )
            return "Done."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self):
            return True

        async def list_models(self):
            return ["obsess-model"]

    @pytest.mark.asyncio
    async def test_path_stuck_obsession_finalizes_turn(self, test_config):
        root = Path(test_config.workspace_root)
        agent = AgentLoop(
            test_config,
            self._PathObsessionProvider(),
            tool_registry=create_default_registry(),
        )
        events = []
        async for event in agent.process_prompt("Write the files", "s1", [], "build"):
            events.append(event)
        assert (root / "a.txt").read_text(encoding="utf-8") == "v1", "first write must win"
        assert (root / "b.txt").read_text(encoding="utf-8") == "b"
        assert (root / "c.txt").read_text(encoding="utf-8") == "c"
        warnings = [e for e in events if e.kind == EventKind.WARNING]
        assert any("kept re-writing" in (e.data.get("message") or "") for e in warnings), (
            "the path-stuck detector must finalize the turn"
        )
        assert events[-1].kind == EventKind.SUCCESS
        assert not any(e.kind == EventKind.ERROR for e in events)
        # The graceful stall summary must list what was written.
        success = [e for e in events if e.kind == EventKind.SUCCESS]
        assert success and "Stopped after" in (success[0].data.get("message") or "")

    class _RecoveringProvider(BaseProvider):
        """Re-writes the same path (blocked), then verifies the written file and
        produces a final summary. The path-stuck detector must NOT finalize while
        the model is still making new progress."""

        def __init__(self):
            super().__init__("recover", "recover-model")
            self.call_count = 0

        async def complete(self, messages, tools=None):
            self.call_count += 1
            n = self.call_count
            if n == 1:
                return (
                    '```tool\n{"tool": "file_write", "params": {"path": "artifact/README.md", '
                    '"content": "Artifacts"}}\n```'
                )
            if n == 2:
                return (
                    '```tool\n{"tool": "file_write", "params": {"path": "artifact/README.md", '
                    '"content": "Artifacts"}}\n'
                    '{"tool": "file_write", "params": {"path": "artifact/README.md", '
                    '"content": "Artifacts"}}\n```'
                )
            if n == 3:
                return (
                    '```tool\n{"tool": "file_read", "params": {"path": "artifact/README.md"}}\n```'
                )
            return "Done."

        async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
            response = await self.complete(messages)
            for char in response:
                yield (char, None)

        async def validate(self):
            return True

        async def list_models(self):
            return ["recover-model"]

    @pytest.mark.asyncio
    async def test_new_progress_after_blocked_rewrites_is_not_stalled(self, test_config):
        root = Path(test_config.workspace_root)
        agent = AgentLoop(
            test_config,
            self._RecoveringProvider(),
            tool_registry=create_default_registry(),
        )
        events = []
        async for event in agent.process_prompt("Create the artifact folder", "s1", [], "build"):
            events.append(event)
        assert (root / "artifact" / "README.md").read_text(encoding="utf-8") == "Artifacts"
        warnings = [e for e in events if e.kind == EventKind.WARNING]
        assert not any("kept re-writing" in (e.data.get("message") or "") for e in warnings), (
            "moving on to a new tool must not trigger the path-stuck finalize"
        )
        assert events[-1].kind == EventKind.SUCCESS
        assert not any(e.kind == EventKind.ERROR for e in events)
        success = [e for e in events if e.kind == EventKind.SUCCESS]
        manifest = success[0].data.get("manifest") or {}
        assert manifest.get("completed") is True, manifest
        assert manifest.get("remaining") == [], manifest
        assert manifest.get("verified") is True, manifest


class TestErrorRecovery:
    @pytest.mark.asyncio
    async def test_recovers_from_provider_error(self, test_config):
        class FailingProvider(BaseProvider):
            def __init__(self):
                super().__init__("fail", "fail-model")

            async def complete(self, messages, tools=None):
                raise RuntimeError("API down")

            async def stream(self, messages, tools=None):
                yield ("should not reach", None)
                raise RuntimeError("API down")

            async def validate(self):
                return False

            async def list_models(self):
                return []

        agent = RecoverableAgentLoop(test_config, FailingProvider())
        events = []
        async for event in agent.process_prompt("Test", "s1", [], "build"):
            events.append(event)
        error_events = [e for e in events if e.kind == EventKind.ERROR]
        assert len(error_events) >= 1
        assert agent.last_error is not None

    @pytest.mark.asyncio
    async def test_recoverable_provider_error(self, test_config):
        from server.domain.errors import ProviderError

        class RateLimitedProvider(BaseProvider):
            def __init__(self):
                super().__init__("rate", "rate-model")

            async def complete(self, messages, tools=None):
                raise ProviderError("Rate limited", provider="rate", recoverable=True)

            async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
                yield ("should not reach", None)
                raise ProviderError("Rate limited", provider="rate", recoverable=True)

            async def validate(self):
                return False

            async def list_models(self):
                return []

        agent = RecoverableAgentLoop(test_config, RateLimitedProvider())
        events = []
        async for event in agent.process_prompt("Test", "s1", [], "build"):
            events.append(event)
        error_events = [e for e in events if e.kind == EventKind.ERROR]
        [e for e in events if e.kind == EventKind.WARNING]
        assert len(error_events) >= 1
        assert any(e.data.get("recoverable") is True for e in error_events)

    @pytest.mark.asyncio
    async def test_recoverable_agent_loop_accepts_repo_map(self, test_config):
        class DummyProvider(BaseProvider):
            def __init__(self):
                super().__init__("dummy", "dummy-model")

            async def complete(self, messages, tools=None):
                return "OK"

            async def stream(self, messages, tools=None):
                yield ("OK", None)

            async def validate(self):
                return True

            async def list_models(self):
                return []

        agent = RecoverableAgentLoop(test_config, DummyProvider())
        events = []
        async for event in agent.process_prompt("Test", "s1", [], mode="plan", repo_map=""):
            events.append(event)


class TestSessionExport:
    def test_export_to_string(self):
        exporter = SessionExporter()
        session = Session(title="Test Session")
        messages = [
            Message(session_id=session.id, role="user", content="Hello"),
            Message(session_id=session.id, role="assistant", content="Hi there!"),
        ]
        md = exporter.export_to_string(session, messages)
        assert "# Test Session" in md
        assert "Hello" in md
        assert "Hi there!" in md

    def test_export_to_file(self, temp_dir):
        exporter = SessionExporter()
        session = Session(title="File Export")
        messages = [Message(session_id=session.id, role="user", content="Test")]
        filepath = exporter.export(session, messages, str(temp_dir / "exports"))
        assert Path(filepath).exists()
        content = Path(filepath).read_text()
        assert "File Export" in content

    def test_export_with_events(self):
        exporter = SessionExporter()
        session = Session(title="Events Test")
        events = [
            Event(kind=EventKind.THINKING, data={"text": "Thinking..."}),
            Event(
                kind=EventKind.TOOL_RESULT,
                data={"tool": "file_write", "success": True, "metadata": {"path": "new.py"}},
            ),
            Event(kind=EventKind.ERROR, data={"message": "Something failed"}),
        ]
        messages = [
            Message(session_id=session.id, role="assistant", content="Result", events=events)
        ]
        md = exporter.export_to_string(session, messages)
        assert "Thinking" in md
        assert "tool_result" in md or "new.py" in md


class TestSkillLoader:
    def test_find_skills(self, temp_dir):
        skills_dir = temp_dir / "agents" / "skills" / "my-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text("# My Skill\nDo things.")
        loader = SkillLoader(str(temp_dir))
        skills = loader.find_skills()
        assert len(skills) == 1
        assert "My Skill" in skills[0]["content"]

    def test_no_skills(self, temp_dir):
        loader = SkillLoader(str(temp_dir))
        skills = loader.find_skills()
        assert len(skills) == 0

    def test_skill_prompt(self, temp_dir):
        skills_dir = temp_dir / "skills" / "test-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text("# Test\nContent here.")
        loader = SkillLoader(str(temp_dir))
        prompt = loader.get_skill_prompt()
        assert "Loaded Skills" in prompt
        assert "skills/test-skill" in prompt

    def test_skill_names(self, temp_dir):
        for name in ["alpha", "beta"]:
            d = temp_dir / "skills" / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"# {name}")
        loader = SkillLoader(str(temp_dir))
        names = loader.get_skill_names()
        assert any("alpha" in n for n in names)
        assert any("beta" in n for n in names)

    def test_skip_hidden_dirs(self, temp_dir):
        hidden = temp_dir / ".hidden" / "skill"
        hidden.mkdir(parents=True)
        (hidden / "SKILL.md").write_text("# Hidden")
        loader = SkillLoader(str(temp_dir))
        skills = loader.find_skills()
        assert len(skills) == 0

    def test_ignores_skills_outside_skill_dirs(self, temp_dir):
        stray = temp_dir / "lib" / "vendor" / "skill"
        stray.mkdir(parents=True)
        (stray / "SKILL.md").write_text("# Stray")
        loader = SkillLoader(str(temp_dir))
        assert loader.find_skills() == []

    def test_skill_prompt_is_metadata_only(self, temp_dir):
        skills_dir = temp_dir / "skills" / "test-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "# Test\n\nA long body that must not be embedded verbatim."
        )
        loader = SkillLoader(str(temp_dir))
        prompt = loader.get_skill_prompt()
        assert "Loaded Skills" in prompt
        assert "skills/test-skill/SKILL.md" in prompt
        assert "long body that must not be embedded verbatim" not in prompt


class TestGracefulShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_calls_cleanup(self):
        shutdown = GracefulShutdown()
        called = []

        async def cleanup():
            called.append(True)

        shutdown.register_cleanup(cleanup)
        await shutdown.shutdown()
        assert len(called) == 1
        assert shutdown.is_shutting_down

    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self):
        shutdown = GracefulShutdown()
        called = []

        async def cleanup():
            called.append(True)

        shutdown.register_cleanup(cleanup)
        await shutdown.shutdown()
        await shutdown.shutdown()
        assert len(called) == 1


class TestContextManagerIntegration:
    def test_build_messages_with_long_history(self, test_config):
        test_config.max_context_tokens = 5000
        ctx = ContextManager(test_config)
        history = [
            Message(session_id="s1", role="user", content=f"Message {i}: " + "word " * 200)
            for i in range(100)
        ]
        messages = ctx.build_messages(history, "System.", "New.", "gpt-4")
        assert len(messages) < 102
        assert messages[-1]["content"] == "New."


class TestRepoMapIntegration:
    def test_structure_and_summary(self, temp_dir):
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "main.py").write_text("print('hello')")
        (temp_dir / "README.md").write_text("# Test")
        repo = RepoMap(str(temp_dir))
        structure = repo.get_structure()
        summary = repo.get_summary()
        assert "Python" in summary
        assert len(structure["children"]) > 0
