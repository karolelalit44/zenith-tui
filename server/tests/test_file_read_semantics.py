"""Phase 0 contracts for file reads and tool-result rendering.

Every test here pins a behaviour that previously produced a *silently wrong*
answer rather than an error. The theme is the same in each case: the model was
told a read or an edit succeeded, and handed nothing that let it tell success
from a no-op.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from server.agents import session_workspace as sw
from server.config.constants import FILE_EDIT_TOOL, MAX_FILE_READ_LINES
from server.toolkit.base import ToolResult
from server.toolkit.executor import build_tool_metadata, format_tool_result
from server.toolkit.registry import current_tool_session_id
from server.toolkit.tools.file_read import FileReadTool, _split_lines

_SESSION = "test-file-read-semantics"


@pytest.fixture
def session_ctx():
    token = current_tool_session_id.set(_SESSION)
    yield _SESSION
    current_tool_session_id.reset(token)


@pytest.fixture(autouse=True)
def _clean_session():
    try:
        yield
    finally:
        sw._READ_CACHE.pop(_SESSION, None)
        sw._STORE.pop(_SESSION, None)


def _read(path: Path, **params):
    return FileReadTool().execute({"path": path.name, **params}, str(path.parent))


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# P0.3  Line counting
# --------------------------------------------------------------------------


class TestLineCounting:
    """`content.split("\\n")` counts the separator after a final newline as a
    line, so every newline-terminated file over-reported by one and the
    pagination hint pointed one line past the end."""

    def test_split_drops_phantom_trailing_line(self):
        assert _split_lines("a\nb\n") == ["a", "b"]
        assert _split_lines("a\nb") == ["a", "b"]
        assert _split_lines("a\n") == ["a"]
        assert _split_lines("") == []
        assert _split_lines("\n") == [""]

    @pytest.mark.asyncio
    async def test_newline_terminated_file_reports_real_line_count(self, temp_dir: Path):
        path = _write(temp_dir / "a.py", "one\ntwo\n")
        result = await _read(path)
        assert result.success
        assert result.metadata["total_lines"] == 2
        assert result.output == "1: one\n2: two"
        assert result.metadata["truncated"] is False

    @pytest.mark.asyncio
    async def test_unterminated_file_reports_same_count(self, temp_dir: Path):
        path = _write(temp_dir / "b.py", "one\ntwo")
        result = await _read(path)
        assert result.metadata["total_lines"] == 2
        assert result.output == "1: one\n2: two"

    @pytest.mark.asyncio
    async def test_empty_file_has_zero_lines_and_says_so(self, temp_dir: Path):
        path = _write(temp_dir / "empty.py", "")
        result = await _read(path)
        assert result.success
        assert result.metadata["total_lines"] == 0
        assert result.metadata["empty"] is True
        # Rendered to the model, an empty body must not read as a silent no-op.
        assert "(no output)" in format_tool_result("file_read", result)

    @pytest.mark.asyncio
    async def test_pagination_hint_lands_on_the_last_real_line(self, temp_dir: Path):
        path = _write(temp_dir / "c.py", "one\ntwo\nthree\n")
        result = await _read(path, limit=2)
        assert result.metadata["total_lines"] == 3
        assert result.metadata["truncated"] is True
        assert "pass offset=2" in result.output

        last = await _read(path, offset=2, limit=10)
        assert last.success
        assert last.output == "3: three"
        assert last.metadata["truncated"] is False


# --------------------------------------------------------------------------
# P0.1  Window validation
# --------------------------------------------------------------------------


class TestWindowValidation:
    """`limit` was only upper-bounded, so a negative value reached
    `lines[offset:offset+limit]` and Python read it as a negative slice,
    returning the file minus its last |limit| lines and reporting success."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [-1, -5, 0])
    async def test_non_positive_limit_is_rejected(self, temp_dir: Path, bad: int):
        path = _write(temp_dir / "a.py", "one\ntwo\n")
        result = await _read(path, limit=bad)
        assert result.success is False
        assert "limit must be >= 1" in result.error

    @pytest.mark.asyncio
    async def test_negative_limit_never_returns_a_slice(self, temp_dir: Path):
        path = _write(temp_dir / "a.py", "\n".join(str(i) for i in range(10)))
        result = await _read(path, limit=-5)
        assert result.success is False
        assert result.output == ""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", ["abc", 1.5j])
    async def test_non_integer_limit_is_rejected_cleanly(self, temp_dir: Path, bad):
        path = _write(temp_dir / "a.py", "one\n")
        result = await _read(path, limit=bad)
        assert result.success is False
        assert "limit must be an integer" in result.error

    @pytest.mark.asyncio
    async def test_negative_offset_is_rejected(self, temp_dir: Path):
        path = _write(temp_dir / "a.py", "one\n")
        result = await _read(path, offset=-1)
        assert result.success is False
        assert "offset must be >= 0" in result.error

    @pytest.mark.asyncio
    async def test_oversized_limit_is_clamped_not_rejected(self, temp_dir: Path):
        path = _write(temp_dir / "a.py", "\n".join(str(i) for i in range(50)))
        result = await _read(path, limit=10**9)
        assert result.success
        assert result.metadata["total_lines"] == 50
        assert result.metadata["showing"] <= MAX_FILE_READ_LINES

    @pytest.mark.asyncio
    async def test_explicit_null_offset_defaults_to_zero(self, temp_dir: Path):
        path = _write(temp_dir / "a.py", "one\ntwo\n")
        result = await _read(path, offset=None)
        assert result.success
        assert result.output.startswith("1: one")


# --------------------------------------------------------------------------
# P0.2  Reading past end of file
# --------------------------------------------------------------------------


class TestOffsetPastEnd:
    """An out-of-range offset produced an empty body, and an empty body was
    dropped by the renderer, so the model received only a SUCCESS header with
    no explanation."""

    @pytest.mark.asyncio
    async def test_past_eof_names_the_highest_valid_offset(self, temp_dir: Path):
        path = _write(temp_dir / "a.py", "one\ntwo\nthree\n")
        result = await _read(path, offset=100)
        assert result.success is False
        assert "past the end" in result.error
        assert "Highest valid offset is 2" in result.error
        assert "3 lines" in result.error

    @pytest.mark.asyncio
    async def test_past_eof_renders_with_the_error_not_a_bare_success(
        self, temp_dir: Path
    ):
        path = _write(temp_dir / "a.py", "one\n")
        result = await _read(path, offset=50)
        rendered = format_tool_result("file_read", result)
        assert "Status: FAILED" in rendered
        assert "past the end" in rendered
        assert "(no output)" not in rendered

    @pytest.mark.asyncio
    async def test_offset_equal_to_line_count_is_past_end(self, temp_dir: Path):
        path = _write(temp_dir / "a.py", "one\ntwo\n")
        result = await _read(path, offset=2)
        assert result.success is False
        assert "Highest valid offset is 1" in result.error


# --------------------------------------------------------------------------
# P0.7  Cache hits are indistinguishable from cold reads
# --------------------------------------------------------------------------


class TestCacheParity:
    """Cache hits replaced the metadata wholesale, so a served read arrived with
    no ``total_lines`` and no continuation hint, and the model could not page."""

    @pytest.mark.asyncio
    async def test_exact_hit_preserves_pagination_state(
        self, temp_dir: Path, session_ctx
    ):
        path = _write(temp_dir / "a.py", "\n".join(f"line {i}" for i in range(1, 101)))
        cold = await _read(path, offset=10, limit=20)
        warm = await _read(path, offset=10, limit=20)

        assert warm.metadata.get("from_cache") is True
        for key in ("total_lines", "showing", "offset", "truncated"):
            assert warm.metadata[key] == cold.metadata[key], key
        assert warm.output == cold.output

    @pytest.mark.asyncio
    async def test_subslice_reports_its_own_window(self, temp_dir: Path, session_ctx):
        path = _write(temp_dir / "a.py", "\n".join(f"line {i}" for i in range(1, 101)))
        await _read(path, offset=0, limit=50)
        sub = await _read(path, offset=10, limit=5)

        assert sub.success
        assert sub.metadata["from_cache"] is True
        assert sub.metadata["offset"] == 10
        assert sub.metadata["showing"] == 5
        assert sub.metadata["total_lines"] == 100
        assert sub.output.startswith("11: line 11")
        # The covering slice was 0-50; the sub-window is not, so it must carry
        # its own continuation hint rather than inheriting a stale one.
        assert "pass offset=15" in sub.output

    @pytest.mark.asyncio
    async def test_subslice_matches_a_cold_read_of_the_same_range(
        self, temp_dir: Path, session_ctx
    ):
        path = _write(temp_dir / "a.py", "\n".join(f"line {i}" for i in range(1, 101)))
        await _read(path, offset=0, limit=50)  # warm the cache
        sub = await _read(path, offset=10, limit=5)

        sw._READ_CACHE.pop(_SESSION, None)  # force a cold read
        cold = await _read(path, offset=10, limit=5)

        assert sub.output == cold.output
        assert {k: v for k, v in sub.metadata.items() if k != "from_cache"} == {
            k: v for k, v in cold.metadata.items() if k != "from_cache"
        }

    @pytest.mark.asyncio
    async def test_subslice_at_end_reports_not_truncated(
        self, temp_dir: Path, session_ctx
    ):
        path = _write(temp_dir / "a.py", "\n".join(f"line {i}" for i in range(1, 21)))
        await _read(path, offset=0, limit=20)
        sub = await _read(path, offset=18, limit=10)
        assert sub.metadata["truncated"] is False
        assert "pass offset=" not in sub.output


# --------------------------------------------------------------------------
# P0.4  Empty results must not read as silent success
# --------------------------------------------------------------------------


class TestEmptyResultIsAnnounced:
    @pytest.mark.asyncio
    async def test_empty_output_gets_an_explicit_marker(self):
        rendered = format_tool_result("list_dir", ToolResult(success=True, output=""))
        assert "(no output)" in rendered
        assert "Status: SUCCESS" in rendered

    @pytest.mark.asyncio
    async def test_non_empty_output_is_untouched(self):
        rendered = format_tool_result("list_dir", ToolResult(success=True, output="a.py"))
        assert "(no output)" not in rendered
        assert "a.py" in rendered

    @pytest.mark.asyncio
    async def test_failure_is_not_labelled_as_empty(self):
        rendered = format_tool_result(
            "file_read", ToolResult(success=False, output="", error="File not found: x")
        )
        assert "(no output)" not in rendered
        assert "Error: File not found: x" in rendered

    @pytest.mark.asyncio
    async def test_output_with_only_whitespace_is_preserved(self):
        rendered = format_tool_result("todo", ToolResult(success=True, output="   "))
        assert "(no output)" not in rendered


# --------------------------------------------------------------------------
# P0.5  Model-visible metadata must not depend on payload size
# --------------------------------------------------------------------------


class TestModelVisibleMetadata:
    @pytest.mark.asyncio
    async def test_a_large_diff_no_longer_hides_pagination_state(self):
        result = ToolResult(
            success=True,
            output="Edited a.py",
            metadata={"total_lines": 120, "showing": 12, "truncated": True,
                      "diff": "x" * 5000},
        )
        rendered = format_tool_result("file_edit", result)
        payload = json.loads(rendered.split("Metadata: ", 1)[1].split(" (+")[0])
        assert payload["total_lines"] == 120
        assert payload["showing"] == 12
        assert payload["truncated"] is True
        assert "diff" not in payload
        assert "omitted" in rendered

    @pytest.mark.asyncio
    async def test_omission_is_announced_when_nothing_survives(self):
        result = ToolResult(success=True, output="x", metadata={"files": ["a", "b"]})
        rendered = format_tool_result("glob", result)
        assert "field(s) omitted" in rendered
        assert "/b/" not in rendered  # the payload is not inlined

    @pytest.mark.asyncio
    async def test_absolute_path_is_not_echoed_to_the_model(self):
        result = ToolResult(
            success=True, output="1: x", metadata={"path": "C:\\a\\very\\long\\root.py"}
        )
        rendered = format_tool_result("file_read", result)
        assert "very\\long" not in rendered

    @pytest.mark.asyncio
    async def test_absurdly_long_scalar_value_is_dropped(self):
        result = ToolResult(success=True, output="x", metadata={"match": "m" * 500})
        rendered = format_tool_result("file_edit", result)
        assert "m" * 500 not in rendered
        assert "omitted" in rendered


# --------------------------------------------------------------------------
# P0.6  The match rung must survive into event metadata
# --------------------------------------------------------------------------


class TestMatchKindPreserved:
    @pytest.mark.parametrize("rung", ["trimmed", "whitespace_normalized"])
    def test_reported_rung_is_not_overwritten(self, rung: str):
        result = ToolResult(
            success=True, output="Edited a.py", metadata={"path": "a.py", "match": rung}
        )
        meta = build_tool_metadata(
            FILE_EDIT_TOOL, {"path": "a.py", "old_content": "x", "new_content": "y"},
            result, 1, ".",
        )
        assert meta["match"] == rung

    def test_defaults_to_exact_when_the_tool_reports_nothing(self):
        result = ToolResult(success=True, output="Edited a.py", metadata={"path": "a.py"})
        meta = build_tool_metadata(
            FILE_EDIT_TOOL, {"path": "a.py", "old_content": "x", "new_content": "y"},
            result, 1, ".",
        )
        assert meta["match"] == "exact"


# --------------------------------------------------------------------------
# P0.8  ANSI stripping is scoped to terminal capture
# --------------------------------------------------------------------------


ESC = "\x1b[31m"


class TestAnsiStrippingIsScoped:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool", ["file_read", "file_edit", "apply_patch", "file_write"])
    async def test_file_content_keeps_its_escape_bytes(self, tool: str):
        result = ToolResult(success=True, output=f"1: print({ESC}red{ESC})")
        assert ESC in format_tool_result(tool, result)

    @pytest.mark.asyncio
    async def test_terminal_output_is_still_stripped(self):
        result = ToolResult(success=True, output=f"{ESC}red{ESC} output")
        rendered = format_tool_result("bash", result)
        assert ESC not in rendered
        assert "red" in rendered
