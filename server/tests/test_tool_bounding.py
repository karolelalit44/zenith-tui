"""The rule that bounds one tool result, and the failure lane inside it.

Bounding a tool result is lossy, so the question is not *whether* to lose
information but *what*. A head/tail trim keeps the first and last lines of a
transcript, which for a failed run is the command echo and the summary â€” the two
parts that do not say what went wrong. The failure lane exists to keep the
diagnosis instead, and these tests pin the cases where it must fire and, just as
importantly, where it must not.

The false-positive tests matter as much as the true ones: exempting ordinary
reads from compaction because their source happens to say ``raise ValueError``
would cost more context than the lane ever saves.
"""

from __future__ import annotations

import pytest

from server.agents.compaction import CompactionStats


def _result(
    body: str,
    *,
    tool: str = "bash",
    status: str = "ok",
    digest: str | None = None,
) -> dict:
    msg = {
        "role": "user",
        "content": f"[Tool: {tool} | Status: {'SUCCESS' if status == 'ok' else 'FAILED'}]\n{body}",
        "tool_name": tool,
        "tool_status": status,
    }
    if digest is not None:
        msg["digest"] = digest
    return msg


NOISE = "\n".join(f"collected item {i} / ok" for i in range(400))


def _failing_log() -> str:
    return (
        "pytest -q tests/\n"
        + NOISE
        + "\n=================================== FAILURES ===================================\n"
        "_______________________________ test_handler[case-7] _______________________________\n"
        + NOISE
        + "\nE       TypeError: build_request() got 2 positional arguments but 3 were given\n"
        "tests/test_x.py:88: in build_request\n"
        + NOISE
        + "\n=========================== 1 failed, 399 passed in 4.21s =========================\n"
    )


class TestFailureDetection:
    @pytest.mark.parametrize(
        "line",
        [
            "Traceback (most recent call last):",
            "E       TypeError: bad thing",
            "AssertionError: 1 != 2",
            "tests/x.ts:3:1 - error TS2345: Argument of type",
            "panic: runtime error: index out of range",
            "--- FAIL: TestThing (0.00s)",
            "error[E0308]: mismatched types",
            "thread 'main' panicked at src/lib.rs:9:5",
            "npm ERR! code ELIFECYCLE",
            "make[1]: *** [Makefile:12: all] Error 2",
            "exit status 1",
            "Segmentation fault",
            "✗ src/index.test.ts",
            "1 failed, 3 passed",
            "FAILED tests/test_x.py::test_y",
        ],
    )
    def test_recognised_failure_vocabulary(self, line):
        from server.agents.compaction import has_failure_report

        assert has_failure_report(f"[Tool: bash | Status: SUCCESS]\n{line}", "bash")

    def test_clean_transcript_is_not_a_failure(self):
        from server.agents.compaction import has_failure_report

        clean = "[Tool: bash | Status: SUCCESS]\n399 passed in 4.2s\n"
        assert has_failure_report(clean, "bash") is False

    def test_structured_status_is_authoritative(self):
        from server.agents.compaction import is_failed_result

        assert is_failed_result(_result("fine", status="error")) is True
        assert is_failed_result(_result("fine", status="ok")) is False

    def test_structured_status_does_not_require_matching_wording(self):
        """The banner is model-facing prose; the stamp is the contract."""
        from server.agents.compaction import is_failed_result

        assert is_failed_result({"role": "user", "content": "anything", "tool_status": "error"})

    def test_unstamped_message_falls_back_to_the_banner(self):
        from server.agents.compaction import is_failed_result

        legacy_ok = {"role": "user", "content": "[Tool: bash | Status: SUCCESS]\nok"}
        legacy_bad = {"role": "user", "content": "[Tool: bash | Status: FAILED]\nboom"}
        assert is_failed_result(legacy_ok) is False
        assert is_failed_result(legacy_bad) is True

    def test_has_failure_report_checks_protocol_status(self):
        from server.agents.compaction import has_failure_report

        assert has_failure_report("[Tool: bash | Status: FAILED]\nboom", "bash") is True
        assert has_failure_report("[Tool: bash | Status: SUCCESS]\nok", "bash") is False

    def test_source_mentioning_errors_is_not_a_failure_report(self):
        """A ``file_read`` payload is code, not a diagnosis of one."""
        from server.agents.compaction import has_failure_report

        src = "[Tool: file_read | Status: SUCCESS]\nraise ValueError('x')\n# SyntaxError\n"
        assert has_failure_report(src, "file_read") is False
        assert has_failure_report(src, "grep") is False

    def test_failure_lines_respect_their_budget(self):
        from server.agents.compaction import FAILURE_LINE_BUDGET, failure_lines

        body = "\n".join(f"ERROR: {i}" for i in range(FAILURE_LINE_BUDGET * 3))
        assert len(failure_lines(body)) == FAILURE_LINE_BUDGET


class TestFailureLane:
    def test_keeps_the_diagnosis_the_generic_lane_would_destroy(self):
        from server.agents.compaction import _bound_ordinary_result, bound_tool_message

        msg = _result(_failing_log(), status="error")
        generic = _bound_ordinary_result(msg["content"], 1000)
        assert "TypeError: build_request" not in generic

        bound_tool_message(msg, 1000)
        assert "TypeError: build_request" in msg["content"]
        assert "test_handler[case-7]" in msg["content"]
        assert "tests/test_x.py" in msg["content"]

    def test_keeps_the_status_header(self):
        from server.agents.compaction import bound_tool_message

        msg = _result(_failing_log(), status="error")
        bound_tool_message(msg, 1000)
        assert msg["content"].startswith("[Tool: bash | Status: FAILED]")

    def test_a_short_failure_is_untouched(self):
        from server.agents.compaction import bound_tool_message

        msg = _result("FAIL: boom\ntrace", status="error")
        bound_tool_message(msg, 1000)
        assert msg["content"] == "[Tool: bash | Status: FAILED]\nFAIL: boom\ntrace"
        assert "time" not in msg

    def test_the_failure_lane_is_dense_where_the_generic_lane_is_not(self):
        """The lane's value is signal per character, not character count.

        A head/tail trim of a long transcript is *longer* than the failure lane
        and almost entirely noise: the run's command echo and its pass count.
        Comparing sizes would rank them the wrong way round.
        """
        from server.agents.compaction import _bound_ordinary_result, bound_tool_message

        msg = _result(_failing_log(), status="error")
        generic = _bound_ordinary_result(msg["content"], 4000)
        bound_tool_message(msg, 4000)

        noise = "collected item 17 / ok"
        assert noise in generic
        assert noise not in msg["content"]
        assert "1 failed, 399 passed" in msg["content"]

    def test_a_failure_below_the_floor_still_keeps_its_diagnosis(self):
        from server.agents.compaction import FAILURE_MIN_CHARS, bound_tool_message

        msg = _result(_failing_log(), status="error")
        bound_tool_message(msg, 1)
        # A 1-char budget cannot carry a diagnosis, so the floor raises it rather
        # than the lane obeying a limit that would make it useless.
        assert FAILURE_MIN_CHARS > 1
        assert "TypeError: build_request" in msg["content"]

    def test_a_failure_respects_its_ceiling(self):
        from server.agents.compaction import bound_failure_result

        body = "\n".join(f"ERROR: detail line {i} " + "x" * 200 for i in range(5000))
        bounded = bound_failure_result(f"[Tool: bash | Status: FAILED]\n{body}", 4000)
        assert len(bounded) <= 4000 + 200
        assert "ERROR: detail line" in bounded
        assert "failure lines omitted" in bounded

    def test_a_passing_run_of_the_same_shape_is_still_bounded(self):
        from server.agents.compaction import bound_tool_message

        msg = _result("pytest -q\n" + NOISE)
        bound_tool_message(msg, 1000)
        assert len(msg["content"]) < len(msg["content"]) + len(NOISE)
        assert len(msg["content"]) < 2000

    def test_structured_error_status_alone_takes_the_lane(self):
        from server.agents.compaction import bound_tool_message

        body = "\n".join(f"diagnostic line {i}" for i in range(300))
        msg = _result(body, tool="file_edit", status="error")
        bound_tool_message(msg, 100)
        assert "diagnostic line" in msg["content"]


class TestBoundingRule:
    def test_is_idempotent(self):
        from server.agents.compaction import bound_tool_message

        msg = _result(_failing_log())
        first = bound_tool_message(msg, 1000)
        assert first.tokens_saved > 0
        assert bound_tool_message(msg, 1000).tokens_saved == 0

    def test_a_message_already_marked_compacted_is_left_alone(self):
        from server.agents.compaction import bound_tool_message

        msg = _result("x" * 5000, digest="short")
        msg["time"] = "compacted"
        bound_tool_message(msg, 100)
        assert len(msg["content"]) > 5000

    def test_digest_lane_is_used_when_available(self):
        from server.agents.compaction import bound_tool_message

        msg = _result("y" * 5000, tool="glob", digest="glob: 3 files")
        bound_tool_message(msg, 100)
        assert msg["content"] == "glob: 3 files"

    def test_content_bearing_tools_are_never_digest_collapsed(self):
        from server.agents.compaction import PRESERVE_ON_COMPACT, bound_tool_message

        for tool in PRESERVE_ON_COMPACT:
            msg = _result("z" * 5000, tool=tool, digest="would lose the content")
            bound_tool_message(msg, 100)
            assert "would lose the content" not in msg["content"]

    def test_ordinary_lane_keeps_the_header(self):
        from server.agents.compaction import bound_tool_message

        msg = _result("a" * 5000, tool="webfetch")
        bound_tool_message(msg, 200)
        assert msg["content"].startswith("[Tool: webfetch | Status: SUCCESS]")
        assert "truncated" in msg["content"]

    def test_small_result_is_untouched(self):
        from server.agents.compaction import bound_tool_message

        msg = _result("tiny", tool="webfetch")
        bound_tool_message(msg, 1000)
        assert msg["content"].endswith("tiny")
        assert "time" not in msg

    def test_stats_describe_the_saving(self):
        from server.agents.compaction import bound_tool_message

        msg = _result("q" * 5000, tool="webfetch")
        stats = bound_tool_message(msg, 500)
        assert stats.trimmed is True
        assert stats.chars_removed == stats.original_chars - stats.compacted_chars
        assert stats.tokens_saved == stats.chars_removed // 4

    def test_non_string_content_is_ignored(self):
        from server.agents.compaction import bound_tool_message

        assert bound_tool_message({"role": "user", "content": None}, 10).tokens_saved == 0


class TestSharedAcrossCallSites:
    """The three bounding passes must agree on any message they both bound.

    They deliberately differ in *scope* — the in-flight pass protects the newest
    N results, the service pass bounds everything older than a turn boundary,
    the live-tail pass bounds the whole tail — so the invariant is per-message,
    not per-total.
    """

    def _fixtures(self) -> list[dict]:
        return [
            _result("a" * 4000, tool="glob", digest="glob: digest"),
            _result(_failing_log()),
            _result("b" * 4000, tool="webfetch"),
            _result("keep me", tool="file_read"),
        ]

    def test_every_pass_bounds_a_message_the_same_way(self):
        """Same rule, each pass at its own budget.

        The passes deliberately differ in scope *and* in budget — the live tail
        is bounded harder than the service pass, which is bounded harder than an
        in-flight render — so the invariant is that at a shared budget they
        produce identical output.
        """
        from server.agents.compaction import bound_tool_message, prune_inflight_messages
        from server.agents.compaction_service import compact_live_tail

        limit = 500
        expected = []
        for m in self._fixtures():
            copy = dict(m)
            bound_tool_message(copy, limit)
            expected.append(copy["content"])

        inflight = prune_inflight_messages(self._fixtures(), keep_latest_tools=0, max_output=limit)[0]
        assert [m["content"] for m in inflight] == expected

        tail = self._fixtures()
        compact_live_tail(tail)
        from server.agents.compaction_service import TAIL_TRIM_MAX_CHARS

        tail_expected = []
        for m in self._fixtures():
            copy = dict(m)
            bound_tool_message(copy, TAIL_TRIM_MAX_CHARS)
            tail_expected.append(copy["content"])
        assert [m["content"] for m in tail] == tail_expected

    def test_service_pass_bounds_in_place_and_reports_a_saving(self):
        from server.agents.compaction_service import prune_tool_outputs

        msgs = self._fixtures()
        stats = prune_tool_outputs(msgs, force_intraturn=True, max_output=500)
        assert stats["count"] > 0
        assert stats["tokens_saved"] > 0
        # The two newest tool results stay at full fidelity.
        assert msgs[-1]["content"].endswith("keep me")

    def test_inflight_pass_does_not_mutate_its_input(self):
        """Re-rendering at a larger budget must recover full-fidelity content."""
        from server.agents.compaction import prune_inflight_messages

        original = self._fixtures()
        before = [dict(m) for m in original]
        prune_inflight_messages(original, keep_latest_tools=0, max_output=100)
        assert original == before

    def test_protecting_everything_bounds_nothing(self):
        from server.agents.compaction import prune_inflight_messages

        msgs = self._fixtures()
        _, stats = prune_inflight_messages(msgs, keep_latest_tools=len(msgs), max_output=100)
        assert stats.tokens_saved == 0

    def test_protecting_none_bounds_every_tool_result(self):
        from server.agents.compaction import prune_inflight_messages

        msgs = self._fixtures()
        _, stats = prune_inflight_messages(msgs, keep_latest_tools=0, max_output=500)
        assert stats.tokens_saved > 0


class TestDeduplication:
    """Reads the conversation already paid for.

    Two reductions, and the second is the one that matters for correctness
    rather than cost: a read that a later edit invalidated is still in context
    describing a version of the file that is gone.
    """

    @staticmethod
    def _m(tool, paths, body="payload " * 200):
        return {
            "role": "user",
            "content": f"[Tool: {tool} | Status: SUCCESS]\n{body}",
            "tool_name": tool,
            "tool_status": "ok",
            "tool_paths": paths,
        }

    def test_a_read_invalidated_by_a_later_edit_is_relabelled(self):
        from server.agents.compaction import dedupe_tool_results

        out, st = dedupe_tool_results([self._m("file_read", ["a.py"]), self._m("file_edit", ["a.py"], "ok")])
        assert "Stale" in out[0]["content"]
        assert st.superseded == 1

    def test_a_read_of_a_file_not_yet_edited_is_untouched(self):
        from server.agents.compaction import dedupe_tool_results

        msgs = [self._m("file_edit", ["a.py"], "ok"), self._m("file_read", ["a.py"])]
        out, st = dedupe_tool_results(msgs)
        assert st.superseded == 0
        assert out[1]["content"] == msgs[1]["content"]

    def test_a_read_after_the_edit_is_the_fresh_one(self):
        """Direction matters: walking newest-first is what gets this right."""
        from server.agents.compaction import dedupe_tool_results

        out, _ = dedupe_tool_results([self._m("file_read", ["a.py"]), self._m("file_edit", ["a.py"], "ok")])
        assert "Stale" in out[0]["content"]
        assert "Stale" not in out[1]["content"]

    def test_a_repeated_read_is_reduced_to_a_pointer(self):
        from server.agents.compaction import dedupe_tool_results

        out, st = dedupe_tool_results([self._m("file_read", ["a.py"]), self._m("file_read", ["./a.py"])])
        assert "already in context" in out[0]["content"]
        assert st.tokens_saved > 0

    def test_relabelling_is_not_counted_as_a_saving(self):
        """A stale notice costs characters. Reporting it as a saving would lie."""
        from server.agents.compaction import dedupe_tool_results

        _, st = dedupe_tool_results([self._m("file_read", ["a.py"]), self._m("file_edit", ["a.py"], "ok")])
        assert st.tokens_saved == 0
        assert st.superseded == 1
        assert st.changed is True

    def test_unrelated_paths_are_left_alone(self):
        from server.agents.compaction import dedupe_tool_results

        msgs = [self._m("file_read", ["a.py"]), self._m("file_read", ["b.py"])]
        out, st = dedupe_tool_results(msgs)
        assert st.changed is False
        assert out == msgs

    def test_inputs_are_never_mutated(self):
        from server.agents.compaction import dedupe_tool_results

        msgs = [self._m("file_read", ["a.py"]), self._m("file_read", ["a.py"])]
        before = [dict(m) for m in msgs]
        dedupe_tool_results(msgs)
        assert msgs == before

    def test_path_spelling_does_not_defeat_matching(self):
        """Separators and prefixes vary; the file does not."""
        from server.agents.compaction import dedupe_tool_results

        out, _ = dedupe_tool_results([self._m("file_read", ["src\\a.py"]), self._m("file_read", ["./src/a.py"])])
        assert "already in context" in out[0]["content"]

    def test_genuinely_different_paths_are_not_merged(self):
        from server.agents.compaction import dedupe_tool_results

        msgs = [self._m("file_read", ["src/a.py"]), self._m("file_read", ["a.py"])]
        out, st = dedupe_tool_results(msgs)
        assert st.changed is False
        assert out[0] is msgs[0] and out[1] is msgs[1]

    def test_messages_without_paths_are_ignored(self):
        from server.agents.compaction import dedupe_tool_results

        legacy = {"role": "user", "content": "[Tool: file_read | Status: SUCCESS]\nold", "tool_name": "file_read"}
        out, st = dedupe_tool_results([legacy, self._m("file_read", ["a.py"])])
        assert st.changed is False
        assert out[0] is legacy

    def test_empty_input(self):
        from server.agents.compaction import dedupe_tool_results

        assert dedupe_tool_results([]) == ([], CompactionStats())
