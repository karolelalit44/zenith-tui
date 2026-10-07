import pytest

from server.agents.summarizer import SUMMARY_TEMPLATE, ConversationSummarizer
from server.config.settings import AppSettings
from server.domain.message import Message
from server.providers.base import BaseProvider


class _EchoProvider(BaseProvider):
    def __init__(self, fail: bool = False):
        super().__init__("test", "test-model")
        self.fail = fail
        self.last_prompt = ""
        self.last_model = None

    async def complete(self, messages, tools=None, model=None) -> str:
        if self.fail:
            raise RuntimeError("down")
        self.last_prompt = messages[-1]["content"]
        self.last_model = model
        return "Objective\n- Implement the auth module\n\nNext Move\n- Write the file_write call"

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        return
        yield

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["test-model"]


class TestConversationSummarizer:
    def _config(self, temp_dir, weak_model=None):
        return AppSettings(
            home_dir=str(temp_dir / "test.db"), workspace_root=str(temp_dir), weak_model=weak_model
        )

    def _msgs(self):
        return [
            Message(session_id="s", role="user", content="build the auth module"),
            Message(session_id="s", role="assistant", content="creating auth.py"),
        ]

    @pytest.mark.asyncio
    async def test_fresh_summary_uses_template(self, temp_dir):
        provider = _EchoProvider()
        s = ConversationSummarizer(self._config(temp_dir), provider)
        out = await s.summarize(self._msgs(), "test-model")
        assert out.startswith("Objective")
        prompt = provider.last_prompt
        assert "Create a short summary" in prompt
        for section in (
            "Objective",
            "Important Details",
            "Work State",
            "Next Move",
            "Relevant Files",
        ):
            assert section in prompt
        assert "first person" in prompt
        assert "<previous-summary>" not in prompt

    @pytest.mark.asyncio
    async def test_anchored_update_merges_previous(self, temp_dir):
        provider = _EchoProvider()
        s = ConversationSummarizer(self._config(temp_dir), provider)
        await s.summarize(self._msgs(), "test-model", previous_summary="Prev: done X")
        prompt = provider.last_prompt
        assert "Update the anchored summary below" in prompt
        assert "<previous-summary>" in prompt
        assert "Prev: done X" in prompt

    @pytest.mark.asyncio
    async def test_empty_messages_returns_empty(self, temp_dir):
        provider = _EchoProvider()
        s = ConversationSummarizer(self._config(temp_dir), provider)
        assert await s.summarize([], "test-model") == ""

    @pytest.mark.asyncio
    async def test_fallback_structured_on_failure(self, temp_dir):
        provider = _EchoProvider(fail=True)
        s = ConversationSummarizer(self._config(temp_dir), provider)
        out = await s.summarize(self._msgs(), "test-model")
        assert "Objective" in out
        assert "auth module" in out or "creating auth.py" in out

    @pytest.mark.asyncio
    async def test_fold_runs_on_the_turn_model(self, temp_dir):
        """The fold runs on the model that produced the work, not a cheaper one.

        The summary is the only record of the tool state and reasoning a later
        turn has to build on, so downgrading the summarizer discards exactly the
        detail the fold exists to preserve. ``weak_model`` stays configured for
        the work it is actually suited to (classification, fetch summarization)
        and must not be applied here.
        """
        provider = _EchoProvider()
        s = ConversationSummarizer(self._config(temp_dir, weak_model="weak-1"), provider)
        await s.summarize(self._msgs(), "turn-model")
        assert provider.last_model == "turn-model"

    @pytest.mark.asyncio
    async def test_fold_preserves_the_turn_usage_ledger(self, temp_dir):
        """Compaction runs inside a turn, so it must not zero the turn's spend.

        ``complete()`` resets the provider's cumulative ledger because it is
        normally a standalone call. Left alone, a mid-turn compaction silently
        zeroes the running totals the turn manifest reports at the end.
        """
        from contextlib import contextmanager

        class _LedgerProvider(_EchoProvider):
            def __init__(self):
                super().__init__()
                self._cumulative_usage = {"prompt_tokens": 2000, "completion_tokens": 400}

            async def complete(self, messages, tools=None, model=None) -> str:
                self._cumulative_usage = {"prompt_tokens": 7, "completion_tokens": 3}
                return await super().complete(messages, tools, model)

            @contextmanager
            def preserve_usage_ledger(self):
                saved = dict(self._cumulative_usage)
                try:
                    yield
                finally:
                    self._cumulative_usage = saved

        provider = _LedgerProvider()
        s = ConversationSummarizer(self._config(temp_dir), provider)
        await s.summarize(self._msgs(), "test-model")
        assert provider._cumulative_usage == {"prompt_tokens": 2000, "completion_tokens": 400}

    @pytest.mark.asyncio
    async def test_focus_instructions_in_fresh_prompt(self, temp_dir):
        provider = _EchoProvider()
        s = ConversationSummarizer(self._config(temp_dir), provider)
        await s.summarize(self._msgs(), "test-model", focus="encryption")
        prompt = provider.last_prompt
        assert "User-specified focus: encryption" in prompt
        assert "relate to this focus" in prompt

    @pytest.mark.asyncio
    async def test_focus_instructions_in_anchored_prompt(self, temp_dir):
        provider = _EchoProvider()
        s = ConversationSummarizer(self._config(temp_dir), provider)
        await s.summarize(
            self._msgs(), "test-model", previous_summary="Prev: done X", focus="file_read caching"
        )
        prompt = provider.last_prompt
        assert "User-specified focus: file_read caching" in prompt
        assert "Update the anchored summary below" in prompt

    @pytest.mark.asyncio
    async def test_blank_focus_adds_no_instructions(self, temp_dir):
        provider = _EchoProvider()
        s = ConversationSummarizer(self._config(temp_dir), provider)
        await s.summarize(self._msgs(), "test-model", focus="   ")
        assert "User-specified focus" not in provider.last_prompt

    def test_template_shape(self):
        assert "Objective" in SUMMARY_TEMPLATE
        assert "Important Details" in SUMMARY_TEMPLATE
        assert "Relevant Files" in SUMMARY_TEMPLATE
