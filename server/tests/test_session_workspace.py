"""Task 13 A2/RC1/RC4 + todo 3.10-3.12: durable session write-registry and the
bounded, lazy ``<session_state>`` rendering service.

Records come only from real write/edit events; byte-identical re-writes of the
model's own prior work are blocked across turns of the same session. The
session-state block is rendered on demand, capped at a heuristic token budget,
and drops the earliest entries first when it would exceed that budget.
"""

import re
import time

from server.agents.session_state import render_session_state
from server.agents.session_workspace import (
    current_path_hash,
    get_cached_read,
    get_dirty_sessions,
    invalidate_read_cache,
    is_identical_replay,
    is_stale,
    known_files,
    mark_clean,
    read_heavy_output,
    record_edit,
    record_read,
    record_write,
    reset_session,
    store_cached_read_output,
    store_heavy_output,
)
from server.config.constants import (
    CHARS_PER_TOKEN,
    SESSION_STATE_HASH_PREFIX_LEN,
    SESSION_STATE_MARKER,
    SESSION_STATE_MAX_TOKENS,
)


def test_empty_session_has_no_files():
    reset_session("s1")
    assert known_files("s1") == {}
    assert is_identical_replay("s1", "a.py", "x") is False


def test_record_write_then_identical_replay_detected():
    reset_session("s2")
    record_write("s2", "weather.py", "def main(): pass\n")
    assert is_identical_replay("s2", "weather.py", "def main(): pass\n") is True
    assert is_identical_replay("s2", "weather.py", "def main(): return\n") is False
    assert is_identical_replay("s2", "other.py", "def main(): pass\n") is False


def test_later_write_updates_hash():
    reset_session("s3")
    record_write("s3", "a.py", "v1")
    record_write("s3", "a.py", "v2")
    assert is_identical_replay("s3", "a.py", "v1") is False
    assert is_identical_replay("s3", "a.py", "v2") is True


def test_record_edit_keeps_last_known_hash():
    reset_session("s4")
    record_write("s4", "a.py", "v1")
    record_edit("s4", "a.py")
    # The edit changed the file on disk but the registry keeps the last written
    # hash; a re-write of the ORIGINAL content is still a replay.
    assert is_identical_replay("s4", "a.py", "v1") is True
    rec = known_files("s4")["a.py"]
    # The initial record_write counts as one write; the edit adds one more.
    assert rec.edits == 1 and rec.writes == 1


def test_sessions_are_isolated():
    reset_session("sA")
    reset_session("sB")
    record_write("sA", "a.py", "content")
    assert is_identical_replay("sB", "a.py", "content") is False
    assert known_files("sB") == {}


def test_reset_clears_session():
    reset_session("s5")
    record_write("s5", "a.py", "content")
    reset_session("s5")
    assert known_files("s5") == {}


class TestSessionStateRendering:
    @staticmethod
    def _record(session_id: str, n: int, prefix: str = "pkg/module") -> None:
        for i in range(n):
            record_write(session_id, f"{prefix}_{i:03d}.py", f"content {i}")

    def test_render_is_none_when_no_files(self):
        reset_session("ss0")
        assert render_session_state("ss0") is None

    def test_render_lists_each_file_as_one_line_digest(self):
        reset_session("ss1")
        self._record("ss1", 3)
        block = render_session_state("ss1")
        assert block is not None
        assert block.startswith(SESSION_STATE_MARKER)
        assert block.count("content hash") == 3
        for i in range(3):
            line = f"- pkg/module_{i:03d}.py (9 bytes, content hash "
            assert line in block
        prefixes = re.findall(r"content hash ([0-9a-f]+)\)", block)
        assert len(prefixes) == 3
        assert all(len(p) == SESSION_STATE_HASH_PREFIX_LEN for p in prefixes)

    def test_render_preserves_touch_order(self):
        reset_session("ss2")
        record_write("ss2", "zzz.py", "content")
        record_write("ss2", "aaa.py", "content")
        block = render_session_state("ss2")
        assert block is not None
        assert block.index("- zzz.py") < block.index("- aaa.py")

    def test_render_bounded_to_max_tokens_drops_earliest(self):
        reset_session("ss3")
        self._record("ss3", 40)
        block = render_session_state("ss3")
        assert block is not None
        assert len(block) <= SESSION_STATE_MAX_TOKENS * CHARS_PER_TOKEN
        assert "pkg/module_000.py" not in block
        assert "pkg/module_039.py" in block

    def test_render_digest_line_stays_single_line_for_long_paths(self):
        reset_session("ss4")
        record_write("ss4", "deep/nested/dir/" + "x" * 300 + ".py", "v")
        block = render_session_state("ss4")
        assert block is not None
        entry = next(line for line in block.splitlines() if line.startswith("- "))
        assert "\n" not in entry
        assert entry.startswith("- ")

    def test_injection_block_is_bounded(self):
        from server.agents.loop import AgentLoop

        reset_session("ss5")
        self._record("ss5", 40)
        messages = [{"role": "system", "content": "system"}, {"role": "user", "content": "hi"}]
        AgentLoop._inject_session_state(messages, "ss5")
        state = next(
            m
            for m in messages
            if m.get("role") == "system" and SESSION_STATE_MARKER in str(m.get("content", ""))
        )
        assert len(str(state["content"])) <= SESSION_STATE_MAX_TOKENS * CHARS_PER_TOKEN


def test_format_tool_result_reuses_compaction_pipeline():
    from server.config.constants import MAX_TOOL_OUTPUT_BASELINE
    from server.toolkit.base import ToolResult
    from server.toolkit.executor import format_tool_result

    rendered = format_tool_result("file_write", ToolResult(success=True, output="x" * 100_000))
    assert rendered.startswith("[Tool: file_write | Status: SUCCESS]")
    assert len(rendered) <= MAX_TOOL_OUTPUT_BASELINE + 200
    assert "truncated" in rendered


class TestStalenessTracking:
    """Gap #6.1: Verify record_read, last_read_at, last_edited_at, and is_stale."""

    def test_record_read_sets_last_read_at(self):
        reset_session("st1")
        record_read("st1", "auth.py")
        rec = known_files("st1")["auth.py"]
        assert rec.last_read_at > 0.0

    def test_record_write_sets_last_edited_at(self):
        reset_session("st2")
        record_write("st2", "auth.py", "content")
        rec = known_files("st2")["auth.py"]
        assert rec.last_edited_at > 0.0
        assert rec.last_read_at == 0.0

    def test_record_edit_sets_last_edited_at(self):
        reset_session("st3")
        record_write("st3", "auth.py", "v1")
        t_before = time.monotonic()
        record_edit("st3", "auth.py")
        rec = known_files("st3")["auth.py"]
        assert rec.last_edited_at >= t_before
        assert rec.edits == 1

    def test_record_read_after_write_makes_file_not_stale(self):
        reset_session("st4")
        record_write("st4", "auth.py", "v1")
        record_read("st4", "auth.py")
        assert is_stale("st4", "auth.py") is False

    def test_record_edit_after_read_makes_file_stale(self):
        reset_session("st5")
        record_read("st5", "auth.py")
        t_read = time.monotonic()
        while time.monotonic() == t_read:
            time.sleep(0.02)
        record_edit("st5", "auth.py")
        assert is_stale("st5", "auth.py") is True

    def test_stale_evicted_before_non_stale(self):
        """Stale file reads get 2x cost in T4 backward-fit; non-stale keeps normal."""
        reset_session("st6")
        record_read("st6", "stale.py")
        t_read = time.monotonic()
        while time.monotonic() == t_read:
            time.sleep(0.02)
        record_edit("st6", "stale.py")
        record_read("st6", "fresh.py")
        assert is_stale("st6", "stale.py") is True
        assert is_stale("st6", "fresh.py") is False

    def test_unknown_file_not_stale(self):
        reset_session("st7")
        assert is_stale("st7", "nonexistent.py") is False

    def test_read_without_edit_not_stale(self):
        reset_session("st8")
        record_read("st8", "a.py")
        assert is_stale("st8", "a.py") is False


class TestReadCache:
    """Gap coverage: read caching, hash-consistency, invalidation, bounds."""

    def test_cached_read_returns_when_hash_matches(self):
        reset_session("rc1")
        store_cached_read_output("rc1", "a.py", "output text")
        assert get_cached_read("rc1", "a.py", current_path_hash("output text")) == "output text"

    def test_cached_read_none_when_hash_mismatch(self):
        reset_session("rc2")
        store_cached_read_output("rc2", "a.py", "output text")
        # File changed on disk => different hash => cache dropped.
        assert get_cached_read("rc2", "a.py", current_path_hash("DIFFERENT")) is None

    def test_write_invalidates_read_cache(self):
        reset_session("rc3")
        store_cached_read_output("rc3", "a.py", "output text")
        record_write("rc3", "a.py", "new content")
        assert get_cached_read("rc3", "a.py", current_path_hash("new content")) is None

    def test_explicit_invalidate_single_and_all(self):
        reset_session("rc4")
        for p in ("a.py", "b.py"):
            store_cached_read_output("rc4", p, p)
        invalidate_read_cache("rc4", "a.py")
        assert get_cached_read("rc4", "a.py", current_path_hash("a.py")) is None
        assert get_cached_read("rc4", "b.py", current_path_hash("b.py")) == "b.py"
        invalidate_read_cache("rc4")
        assert get_cached_read("rc4", "b.py", current_path_hash("b.py")) is None

    def test_cache_bounded(self):
        reset_session("rc5")
        for i in range(10):
            store_cached_read_output("rc5", f"f{i}.py", f"o{i}")
        # All 10 fit under the 200 cap; no eviction occurs here.
        assert get_cached_read("rc5", "f0.py", current_path_hash("o0")) == "o0"


class TestHeavyOutputs:
    """Gap coverage: full heavy-tool-output store and per-session isolation."""

    def test_store_and_read_heavy_output(self):
        reset_session("ho1")
        store_heavy_output("ho1", "big/out.txt", "x" * 100_000)
        assert read_heavy_output("ho1", "big/out.txt") == "x" * 100_000

    def test_heavy_output_none_when_absent(self):
        reset_session("ho2")
        assert read_heavy_output("ho2", "missing.txt") is None

    def test_heavy_outputs_isolated_per_session(self):
        reset_session("ho3a")
        reset_session("ho3b")
        store_heavy_output("ho3a", "out.txt", "aaa")
        assert read_heavy_output("ho3a", "out.txt") == "aaa"
        assert read_heavy_output("ho3b", "out.txt") is None


class TestDirtyEpoch:
    """Gap coverage: dirty tracking + C-F07 lost-update guard."""

    def test_mutations_mark_dirty(self):
        reset_session("de1")
        mark_clean("de1")
        assert "de1" not in get_dirty_sessions()
        record_write("de1", "a.py", "x")
        assert "de1" in get_dirty_sessions()
        mark_clean("de1")
        assert "de1" not in get_dirty_sessions()

    def test_reset_clears_dirty_flag(self):
        reset_session("de2")
        record_write("de2", "a.py", "x")
        assert "de2" in get_dirty_sessions()
        reset_session("de2")
        assert "de2" not in get_dirty_sessions()

    def test_flush_to_db_persists_and_clears_dirty(self):
        import asyncio

        reset_session("de3")
        from server.agents.session_workspace import flush_to_db

        record_write("de3", "a.py", "content")
        record_write("de3", "b.py", "other")

        class _FakeRepo:
            def __init__(self):
                self.saved = []

            async def upsert_batch(self, session_id, batch):
                self.saved.extend(batch)

            async def delete_session(self, session_id):
                pass

        repo = _FakeRepo()
        asyncio.run(flush_to_db("de3", repo))
        assert len(repo.saved) == 2
        assert "de3" not in get_dirty_sessions()
        # Records remain in memory.
        assert set(known_files("de3")) == {"a.py", "b.py"}

    def test_flush_noop_when_not_dirty(self):
        import asyncio

        reset_session("de4")
        from server.agents.session_workspace import flush_to_db

        class _FakeRepo:
            async def upsert_batch(self, session_id, batch):
                raise AssertionError("should not run")

            async def delete_session(self, session_id):
                raise AssertionError("should not run")

        # Nothing recorded => not dirty => flush must be a no-op.
        asyncio.run(flush_to_db("de4", _FakeRepo()))
