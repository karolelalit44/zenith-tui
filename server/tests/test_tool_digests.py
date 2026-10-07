from __future__ import annotations

from server.agents.loop import _strip_write_payload_from_assistant_messages
from server.config.constants import EPHEMERAL_TOOL_WINDOW_SIZE, TOOL_DIGEST_MAX_CHARS
from server.toolkit.base import ToolResult
from server.toolkit.digest import format_tool_digest


class TestToolDigestFormatter:
    def test_digest_glob_success(self):
        result = ToolResult(
            success=True,
            output="file1.py\nfile2.py\nfile3.py",
            metadata={"count": 3},
        )
        digest = format_tool_digest("glob", {"pattern": "*.py", "path": "server"}, result)
        assert "[Tool: glob | Status: SUCCESS]" in digest
        assert "Found 3 files matching '*.py' in 'server'" in digest

    def test_digest_grep_success(self):
        result = ToolResult(
            success=True,
            output="server/a.py:10: def foo():\nserver/b.py:20: def foo():",
            metadata={"count": 2, "files_searched": 5},
        )
        digest = format_tool_digest("grep", {"pattern": "def foo"}, result)
        assert "[Tool: grep | Status: SUCCESS]" in digest
        assert "Found 2 matches for 'def foo' across 5 file(s)" in digest

    def test_digest_file_read_success(self):
        lines = "\n".join(f"line {i}" for i in range(50))
        result = ToolResult(success=True, output=lines)
        digest = format_tool_digest("file_read", {"path": "server/main.py"}, result)
        assert "[Tool: file_read | Status: SUCCESS]" in digest
        assert "Read 50 lines from 'server/main.py'" in digest

    def test_digest_file_write_success(self):
        result = ToolResult(success=True, output="Successfully wrote 4.8 KB")
        digest = format_tool_digest(
            "file_write",
            {"path": "plan.md", "content": "# Plan\n" + "x" * 4800},
            result,
        )
        assert "[Tool: file_write | Status: SUCCESS]" in digest
        assert "Wrote 4.7 KB to 'plan.md'" in digest or "Wrote 4.8 KB to 'plan.md'" in digest

    def test_digest_file_edit_success(self):
        result = ToolResult(success=True, output="Edit applied")
        digest = format_tool_digest("file_edit", {"path": "server/loop.py"}, result)
        assert "[Tool: file_edit | Status: SUCCESS]" in digest
        assert "Applied edit to 'server/loop.py'" in digest

    def test_digest_bash_success(self):
        result = ToolResult(
            success=True,
            output="test session starts\n664 passed in 10s",
            metadata={"exit_code": 0},
        )
        digest = format_tool_digest(
            "bash",
            {"command": "pytest server/tests"},
            result,
        )
        assert "[Tool: bash | Status: SUCCESS]" in digest
        assert "Executed 'pytest server/tests' -> exit 0" in digest

    def test_digest_error_preserves_failure_reason(self):
        result = ToolResult(success=False, error="File not found: missing.py")
        digest = format_tool_digest("file_read", {"path": "missing.py"}, result)
        assert "[Tool: file_read | Status: FAILED]" in digest
        assert "Error: File not found: missing.py" in digest

    def test_digest_hard_char_ceiling(self):
        result = ToolResult(
            success=False,
            error="Very long error message " * 50,
        )
        digest = format_tool_digest("custom", {}, result)
        assert len(digest) <= TOOL_DIGEST_MAX_CHARS


class TestEphemeralWindowAndPayloadStripping:
    def test_strip_write_payload_from_assistant_messages(self):
        large_json = (
            '{"tool": "file_write", "params": {"path": "plan.md", "content": "' + "A" * 2000 + '"}}'
        )
        messages = [
            {"role": "user", "content": "Write plan.md"},
            {"role": "assistant", "content": large_json},
            {"role": "user", "content": "Wrote plan.md"},
        ]
        _strip_write_payload_from_assistant_messages(messages, "plan.md")
        assistant_content = messages[1]["content"]
        assert "A" * 2000 not in assistant_content
        assert "[content omitted; file written]" in assistant_content

    def test_sliding_window_compaction(self):
        """The window keeps the newest EPHEMERAL_TOOL_WINDOW_SIZE results intact.

        Exercises `prune_inflight_messages` itself. The previous version of this
        test re-implemented the digest rule inline and then asserted against its
        own reimplementation, so it passed regardless of production behaviour.
        """
        from server.agents.compaction import prune_inflight_messages

        messages: list[dict] = [
            {
                "role": "user",
                "content": f"FULL OUTPUT FOR TOOL {i} " + "X" * 1000,
                "digest": f"[Tool: tool_{i} | Status: SUCCESS] Found {i} items",
                "tool_name": f"tool_{i}",
            }
            for i in range(EPHEMERAL_TOOL_WINDOW_SIZE + 2)
        ]

        pruned, stats = prune_inflight_messages(
            messages, keep_latest_tools=EPHEMERAL_TOOL_WINDOW_SIZE
        )

        assert stats.trimmed is True
        # Everything outside the window is collapsed onto its digest.
        digested = EPHEMERAL_TOOL_WINDOW_SIZE
        for i in range(digested):
            assert pruned[i]["content"] == f"[Tool: tool_{i} | Status: SUCCESS] Found {i} items"
            assert "X" * 1000 not in pruned[i]["content"]
            assert pruned[i]["time"] == "compacted"
        # The window itself retains full output.
        for i in range(digested, len(messages)):
            assert pruned[i]["content"].startswith(f"FULL OUTPUT FOR TOOL {i}")
