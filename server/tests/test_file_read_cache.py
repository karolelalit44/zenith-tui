from __future__ import annotations

from pathlib import Path

import pytest

from server.agents import session_workspace as sw
from server.toolkit.registry import current_tool_session_id
from server.toolkit.tools.file_read import FileReadTool


@pytest.fixture
def session_ctx():
    token = current_tool_session_id.set("test-session-read-cache")
    yield "test-session-read-cache"
    current_tool_session_id.reset(token)


@pytest.fixture(autouse=True)
def _clean_session():
    try:
        yield
    finally:
        sw._READ_CACHE.pop("test-session-read-cache", None)
        sw._STORE.pop("test-session-read-cache", None)


def _write(path: Path, lines: int, prefix: str = "line") -> str:
    text = "\n".join(f"{prefix}_{i} = {i}" for i in range(1, lines + 1))
    path.write_text(text)
    return text


class TestReadCacheHit:
    @pytest.mark.asyncio
    async def test_second_read_returns_cached_output(self, temp_dir: Path, session_ctx):
        path = temp_dir / "a.py"
        _write(path, 300)

        tool = FileReadTool()
        first = await tool.execute({"path": "a.py"}, str(temp_dir))
        second = await tool.execute({"path": "a.py"}, str(temp_dir))

        assert first.success and second.success
        assert second.metadata.get("from_cache") is True
        assert first.output == second.output

    @pytest.mark.asyncio
    async def test_cache_hit_skips_disk_io(self, temp_dir: Path, session_ctx, monkeypatch):
        path = temp_dir / "b.py"
        _write(path, 50)

        reads = {"count": 0}
        original_read_text = Path.read_text

        def counting_read_text(self: Path, **kwargs):
            reads["count"] += 1
            return original_read_text(self, **kwargs)

        monkeypatch.setattr(Path, "read_text", counting_read_text)

        tool = FileReadTool()
        await tool.execute({"path": "b.py"}, str(temp_dir))
        await tool.execute({"path": "b.py"}, str(temp_dir))

        assert reads["count"] == 1

    @pytest.mark.asyncio
    async def test_no_session_id_bypasses_cache(self, temp_dir: Path):
        path = temp_dir / "c.py"
        _write(path, 20)

        tool = FileReadTool()
        first = await tool.execute({"path": "c.py"}, str(temp_dir))
        second = await tool.execute({"path": "c.py"}, str(temp_dir))

        assert first.success and second.success
        assert second.metadata.get("from_cache") is not True

    @pytest.mark.asyncio
    async def test_subslice_served_from_cache(self, temp_dir: Path, session_ctx, monkeypatch):
        path = temp_dir / "d.py"
        _write(path, 200)

        reads = {"count": 0}
        original_read_text = Path.read_text

        def counting_read_text(self: Path, **kwargs):
            reads["count"] += 1
            return original_read_text(self, **kwargs)

        monkeypatch.setattr(Path, "read_text", counting_read_text)

        tool = FileReadTool()
        full = await tool.execute({"path": "d.py"}, str(temp_dir))
        assert full.metadata.get("from_cache") is not True
        assert reads["count"] == 1

        paged = await tool.execute({"path": "d.py", "offset": 50, "limit": 25}, str(temp_dir))
        assert paged.metadata.get("from_cache") is True
        assert "51: line_51 = 51" in paged.output
        assert "75: line_75 = 75" in paged.output
        assert reads["count"] == 1


class TestReadCacheInvalidation:
    @pytest.mark.asyncio
    async def test_write_invalidates_cache(self, temp_dir: Path, session_ctx):
        path = temp_dir / "e.py"
        path.write_text("old = 1\n")

        tool = FileReadTool()
        first = await tool.execute({"path": "e.py"}, str(temp_dir))
        assert first.metadata.get("from_cache") is not True

        # Writing new content changes mtime and size — the cache fingerprint no
        # longer matches so the next read must hit disk, not the cache.
        (temp_dir / "e.py").write_text("old = 1\nnew = 2\nx = 3\n")

        second = await tool.execute({"path": "e.py"}, str(temp_dir))
        assert second.metadata.get("from_cache") is not True
        assert "new = 2" in second.output

    @pytest.mark.asyncio
    async def test_size_change_invalidates_cache(self, temp_dir: Path, session_ctx):
        path = temp_dir / "f.py"
        path.write_text("v = 1\n")

        tool = FileReadTool()
        first = await tool.execute({"path": "f.py"}, str(temp_dir))
        assert first.metadata.get("from_cache") is not True

        path.write_text("v = 1\nv = 2\nv = 3\n")
        second = await tool.execute({"path": "f.py"}, str(temp_dir))
        assert second.metadata.get("from_cache") is not True
        assert "v = 3" in second.output


class TestRangeCoverage:
    def test_fully_covered_range(self):
        sid = "test-session"
        sw.cache_file_read(sid, "x.py", 0, 250, "c", mtime_ns=1, size=10, total_lines=500)
        assert sw.is_range_covered(sid, "x.py", 0, 250) is True
        assert sw.is_range_covered(sid, "x.py", 50, 100) is True

    def test_partial_overlap_not_covered(self):
        sid = "test-session"
        sw.cache_file_read(sid, "x.py", 0, 250, "c", mtime_ns=1, size=10, total_lines=500)
        assert sw.is_range_covered(sid, "x.py", 200, 300) is False
        assert sw.is_range_covered(sid, "x.py", 251, 10) is False

    def test_history_tracks_distinct_ranges(self):
        sid = "test-session"
        sw.cache_file_read(sid, "h.py", 0, 250, "c", mtime_ns=1, size=10, total_lines=600)
        sw.cache_file_read(sid, "h.py", 0, 250, "c", mtime_ns=1, size=10, total_lines=600)
        sw.cache_file_read(sid, "h.py", 250, 250, "c2", mtime_ns=1, size=10, total_lines=600)
        history = sw.get_read_history(sid, "h.py")
        assert history == [(0, 250), (250, 250)]

    def test_stale_fingerprint_evicts_entry(self):
        """A fingerprint mismatch (changed mtime/size) must evict the cache entry."""
        sid = "test-session"
        sw.cache_file_read(sid, "/abs/i.py", 0, 250, "c", mtime_ns=1, size=10, total_lines=500)
        assert sw.is_range_covered(sid, "/abs/i.py", 0, 250)
        # Simulate file change: different mtime_ns causes get_cached_read to evict.
        result = sw.get_cached_read(sid, "/abs/i.py", 0, 250, mtime_ns=999, size=10)
        assert result is None
        assert not sw.is_range_covered(sid, "/abs/i.py", 0, 250)
        assert sw.get_read_history(sid, "/abs/i.py") == []


class TestUpperBoundEviction:
    def test_cache_bounded_per_session(self):
        sid = "test-session"
        for i in range(sw._MAX_READ_CACHE_ENTRIES + 10):
            sw.cache_file_read(sid, f"f{i}.py", 0, 250, "c", mtime_ns=1, size=10, total_lines=300)
        paths = sw._READ_CACHE.get(sid, {})
        assert len(paths) <= sw._MAX_READ_CACHE_ENTRIES + 1