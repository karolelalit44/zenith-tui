"""Module 05 additive interface-lock: live output streaming + wait-for-completion.

Reference: opencode/bash.ts streams output chunks as they arrive, then
transitions running -> completed; codex ExecCommandOutputDelta runs until done /
timeout / cancelled. Additive — the buffering background+poll path stays for Phase 2.
"""

import asyncio
import platform

import pytest

from server.shell_runner import ShellStreamEvent, run_shell_command_streamed

_IS_WINDOWS = platform.system() == "Windows"


async def _collect(command: str, **kw) -> list[ShellStreamEvent]:
    return [ev async for ev in run_shell_command_streamed(command, **kw)]


def _run(command: str, **kw) -> list[ShellStreamEvent]:
    return asyncio.run(_collect(command, **kw))


def _echo_word():
    return "Write-Output streamed_hello" if _IS_WINDOWS else "echo streamed_hello"


def _sleep_cmd(seconds=5):
    if _IS_WINDOWS:
        return f"Start-Sleep -Seconds {seconds}"
    return f"sleep {seconds}"


class TestStreamingRunner:
    def test_yields_output_chunks_then_exit_event(self):
        events = _run(_echo_word())
        kinds = [ev.kind for ev in events]
        assert kinds[-1] == "exit"
        assert events[-1].exit_code == 0
        text = "".join(ev.data for ev in events if ev.kind in ("stdout", "stderr"))
        assert "streamed_hello" in text

    def test_stderr_is_surfaced(self):
        if _IS_WINDOWS:
            cmd = "Write-Error streamed_err_input"
        else:
            cmd = "echo streamed_err_input >&2"
        events = _run(cmd)
        text = "".join(ev.data for ev in events if ev.kind in ("stdout", "stderr"))
        assert "streamed_err_input" in text

    def test_exit_code_captured_on_failure(self):
        cmd = "exit 3" if not _IS_WINDOWS else "exit(3)"
        events = _run(cmd)
        exit_event = events[-1]
        assert exit_event.kind == "exit"
        assert exit_event.exit_code != 0

    def test_timeout_kills_and_raises(self):
        with pytest.raises(asyncio.TimeoutError):
            events = _run(_sleep_cmd(5), timeout=0.3)
            # Ensure the generator is fully consumed / closed (raise happens inside).
            for _ in events:
                pass


class TestStreamingContract:
    def test_all_chunks_then_single_exit(self):
        # The stream delivers data chunks first (in order) and terminates with
        # exactly one exit event whose exit_code reflects the process result.
        events = _run(_echo_word())
        data_events = [ev for ev in events if ev.kind in ("stdout", "stderr")]
        exit_events = [ev for ev in events if ev.kind == "exit"]
        assert len(exit_events) == 1
        assert exit_events[0].exit_code == 0
        assert data_events  # at least one live chunk was emitted
        # Chunks arrive before the exit event (not after a full buffer flush).
        assert events.index(exit_events[0]) == len(events) - 1
