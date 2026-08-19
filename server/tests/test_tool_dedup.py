"""QA-2: tool dedup via path canonicalization + content-aware cached reads.

Covers:
- ``_call_signature`` produces the same identity for ``foo.py``, ``./foo.py``
  and ``<workspace>/foo.py`` (workspace-relative vs absolute).
- The loop does not re-execute a read of the same file spelled differently.
- Unchanged repeated reads return a compact cached-read result instead of
  re-reading the full content.
"""

import json
from pathlib import Path

import pytest

from server.agents.loop import AgentLoop, _call_signature
from server.agents.loop_detection import _compute_signature
from server.config.providers import ProviderConfig
from server.config.settings import AppSettings
from server.domain.events import EventKind
from server.providers.base import BaseProvider
from server.toolkit import create_default_registry


def _make_config(temp_dir):
    return AppSettings(
        providers={"test": ProviderConfig(model="test-model", is_active=True)},
        active_provider="test",
        db_path=str(temp_dir / "test.db"),
        workspace_root=str(temp_dir),
    )


# ---------------------------------------------------------------------------
# _call_signature canonical identity
# ---------------------------------------------------------------------------


def test_call_signature_equivalent_paths_are_identical(tmp_path):
    ws = str(tmp_path)
    (tmp_path / "sessions.py").write_text("print('hi')\n", encoding="utf-8")
    a = _call_signature("file_read", {"path": "sessions.py"}, ws)
    b = _call_signature("file_read", {"path": "./sessions.py"}, ws)
    c = _call_signature("file_read", {"path": str(tmp_path / "sessions.py")}, ws)
    assert a == b == c


def test_call_signature_non_path_params_unaffected(tmp_path):
    ws = str(tmp_path)
    s1 = _call_signature("bash", {"command": "ls -la"}, ws)
    s2 = _call_signature("bash", {"command": "ls -la"}, ws)
    s3 = _call_signature("bash", {"command": "ls -lb"}, ws)
    assert s1 == s2
    assert s1 != s3


def test_loop_detector_signature_canonicalizes_paths(tmp_path):
    ws = str(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    sig1 = _compute_signature("file_read", {"path": "a.py"}, "1: x = 1", ws)
    sig2 = _compute_signature("file_read", {"path": "./a.py"}, "1: x = 1", ws)
    sig3 = _compute_signature("file_read", {"path": str(tmp_path / "a.py")}, "1: x = 1", ws)
    assert sig1 == sig2 == sig3


def test_loop_detector_signature_distinguishes_different_paths(tmp_path):
    ws = str(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")
    sig_a = _compute_signature("file_read", {"path": "a.py"}, "1: x = 1", ws)
    sig_b = _compute_signature("file_read", {"path": "b.py"}, "1: y = 2", ws)
    assert sig_a != sig_b


# ---------------------------------------------------------------------------
# Cached-read helpers
# ---------------------------------------------------------------------------


def test_cached_read_returns_only_when_unchanged():
    from server.agents import session_workspace as sw

    sw.reset_session("s-cache")
    sw.store_cached_read_output("s-cache", "data.txt", "line1\nline2")
    current = "line1\nline2"
    hit = sw.cached_read_for("s-cache", "data.txt", sw.current_path_hash(current))
    assert hit == "line1\nline2"
    # Changed content -> no cache hit.
    changed = "line1\nCHANGED"
    miss = sw.cached_read_for("s-cache", "data.txt", sw.current_path_hash(changed))
    assert miss is None


def test_cached_read_invalidated_on_write():
    from server.agents import session_workspace as sw

    sw.reset_session("s-cache2")
    sw.store_cached_read_output("s-cache2", "data.txt", "old content")
    sw.record_write("s-cache2", "data.txt", "new content")
    hit = sw.cached_read_for("s-cache2", "data.txt", sw.current_path_hash("new content"))
    assert hit is None


# ---------------------------------------------------------------------------
# Loop-level: repeated reads of the same file dedupe and use the cache
# ---------------------------------------------------------------------------


class _ReadThenRepeatAbsoluteProvider(BaseProvider):
    """Issues the same file_read twice, second time with an absolute path."""

    def __init__(self, workspace_root: str):
        super().__init__("test", "test-model")
        self._workspace_root = workspace_root
        self.call_count = 0

    async def complete(self, messages, tools=None):
        self.call_count += 1
        if self.call_count == 1:
            payload = {"tool": "file_read", "params": {"path": "data.txt"}}
        else:
            abs_path = str((Path(self._workspace_root) / "data.txt").resolve())
            payload = {"tool": "file_read", "params": {"path": abs_path}}
        # Emit properly JSON-escaped payloads (as a real model does). On
        # Windows the absolute path contains backslashes; leaving them raw would
        # make the JSON parser treat ``\t`` as a tab escape and corrupt the path.
        return f"```tool\n{json.dumps(payload)}\n```"

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        response = await self.complete(messages)
        for char in response:
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["test-model"]


@pytest.mark.asyncio
async def test_loop_dedupes_equivalent_path_reads(tmp_path):
    (tmp_path / "data.txt").write_text("hello world\n", encoding="utf-8")
    config = _make_config(tmp_path)
    provider = _ReadThenRepeatAbsoluteProvider(str(tmp_path))
    agent = AgentLoop(config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("read data.txt", "s1", [], "build"):
        events.append(event)

    # The second (absolute-path) read must be treated as a repeat of the first
    # and not re-executed: only one file_read actually executes.
    executed_reads = [
        e for e in events if e.kind == EventKind.TOOL_RESULT and e.data.get("tool") == "file_read"
    ]
    assert len(executed_reads) <= 1, f"expected deduped read, got {len(executed_reads)}"
    assert events[-1].kind == EventKind.SUCCESS
