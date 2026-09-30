import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from server.agents.context import ContextManager
from server.config.constants import CHARS_PER_TOKEN, DEFAULT_CONTEXT_WINDOW
from server.config.settings import AppSettings
from server.domain.message import Message
from server.providers.token_counter import TokenCounter
from server.workspace.repo_map import RepoMap


def _resumed_history():
    return [Message(session_id="s1", role="user", content="Earlier prompt")]


def _write(workspace: Path, rel: str, content: str) -> None:
    p = workspace / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


@pytest.fixture
def sample_workspace(temp_dir):
    _write(
        temp_dir,
        "src/utils.py",
        "def helper_a():\n pass\n\ndef helper_b():\n pass\n\ndef helper_c():\n pass\n\ndef helper_d():\n pass\n",
    )
    _write(
        temp_dir,
        "src/main.py",
        "from utils import helper_a, helper_b, helper_c, helper_d\n\ndef main():\n return helper_a()\n",
    )
    _write(
        temp_dir,
        "src/mod_a.py",
        "from utils import helper_b\n\ndef mod_a_fn():\n return helper_b()\n",
    )
    _write(
        temp_dir,
        "src/mod_b.py",
        "from utils import helper_c, helper_d\n\ndef mod_b_fn():\n return helper_c()\n",
    )
    _write(temp_dir, "README.md", "# Sample\n\nContent here.\n")
    return temp_dir


def _estimated_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def test_repo_map_is_token_bounded(sample_workspace):
    repo = RepoMap(sample_workspace)
    result = repo.get_repo_map(max_tokens=1000)
    assert "Directory Structure" in result
    assert "Key Definitions" in result
    assert _estimated_tokens(result) <= 1000 + 16


def test_repo_map_ranks_most_referenced_file_first(sample_workspace):
    repo = RepoMap(sample_workspace)
    result = repo.get_repo_map(max_tokens=10000)
    defs_section = result.split("Key Definitions:")[1]
    first_line = defs_section.strip().splitlines()[0]
    assert "utils.py" in first_line
    assert "utils.py" in defs_section


def test_repo_map_honors_small_budget(sample_workspace):
    repo = RepoMap(sample_workspace)
    result = repo.get_repo_map(max_tokens=200)
    assert _estimated_tokens(result) <= 200 + 16
    assert result.strip()


def _make_config(temp_dir, **overrides) -> AppSettings:
    defaults: dict[str, Any] = {
        "home_dir": str(temp_dir / "test.db"),
        "workspace_root": str(temp_dir),
        "max_context_tokens": DEFAULT_CONTEXT_WINDOW,
        "repo_map_tokens": 2000,
    }
    defaults.update(overrides)
    return AppSettings(**defaults)


def test_build_messages_injects_repo_map(sample_workspace):
    config = _make_config(sample_workspace)
    cm = ContextManager(config)
    messages = cm.build_messages(
        _resumed_history(),
        system_prompt="SYS",
        new_prompt="hi",
        model="test-model",
        repo_map="src/main.py:\n main (line 1)",
    )
    assert messages[0] == {"role": "system", "content": "SYS"}
    assert messages[1]["role"] == "system"
    assert "<repo_map>" in messages[1]["content"]
    assert messages[-1]["content"] == "hi"


def test_build_messages_injects_repo_map_on_a_fresh_session(sample_workspace):
    """The first turn is when the map matters most, so it is not withheld.

    It used to be dropped until history existed, to save the tokens it costs.
    But the turn with no history is the one where the model has no idea where it
    is, and a map that arrives only once the model has already started guessing
    arrives after the guess has shaped its next move.
    """
    config = _make_config(sample_workspace)
    cm = ContextManager(config)
    messages = cm.build_messages(
        history=[],
        system_prompt="SYS",
        new_prompt="hi",
        model="test-model",
        repo_map="src/main.py:\n main (line 1)",
    )
    assert len(messages) == 3
    assert any("<repo_map>" in m["content"] for m in messages)
    assert messages[0]["content"] == "SYS"
    assert messages[-1]["content"] == "hi"


def test_build_messages_merges_map_when_no_system_role(sample_workspace):
    config = _make_config(sample_workspace)
    cm = ContextManager(config)
    messages = cm.build_messages(
        _resumed_history(),
        system_prompt="SYS",
        new_prompt="hi",
        model="test-model",
        use_system_prompt=False,
        repo_map="src/utils.py:\n helper_a (line 1)",
    )
    assert all(m["role"] != "system" for m in messages)
    assert len(messages) == 1
    content = messages[0]["content"]
    assert content.startswith("SYS")
    assert "<repo_map>" in content
    assert content.endswith("hi")


def test_repo_map_disabled(sample_workspace):
    config = _make_config(sample_workspace, repo_map_enabled=False)
    cm = ContextManager(config)
    messages = cm.build_messages(
        history=[], system_prompt="SYS", new_prompt="hi", model="test-model"
    )
    assert len(messages) == 2
    assert all("<repo_map>" not in m["content"] for m in messages)
    assert cm.get_repo_map() == ""


def test_get_repo_map_cached_per_instance(sample_workspace):
    config = _make_config(sample_workspace)
    cm = ContextManager(config)
    first = cm.get_repo_map()
    second = cm.get_repo_map()
    assert first == second
    assert "<repo_map>" not in first
    assert "Directory Structure" in first


def test_repo_map_tokens_counted_in_budget(sample_workspace):
    config = _make_config(sample_workspace, max_context_tokens=2000)
    cm = ContextManager(config)
    info_before = cm.get_token_info(
        cm.build_messages(
            _resumed_history(),
            system_prompt="SYS",
            new_prompt="hi",
            model="test-model",
            repo_map="",
        ),
        "test-model",
    )
    info_with = cm.get_token_info(
        cm.build_messages(
            _resumed_history(),
            system_prompt="SYS",
            new_prompt="hi",
            model="test-model",
            repo_map="src/main.py:\n main (line 1)",
        ),
        "test-model",
    )
    assert info_with.used > info_before.used


def _init_git_repo(path: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def run(*args: str) -> None:
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@test",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@test",
        }
        subprocess.run(
            ["git"] + list(args), cwd=str(path), check=True, capture_output=True, text=True, env=env
        )

    run("init", "-q")
    run("config", "user.email", "test@test")
    run("config", "user.name", "test")
    run("add", "-A")
    run("commit", "-q", "-m", "init")


def test_git_aware_excludes_large_untracked_dir(temp_dir):
    _init_git_repo(temp_dir, {"src/a.py": "def a():\n    pass\n"})
    huge = temp_dir / "ref_repo" / "big"
    huge.mkdir(parents=True)
    (huge / "b.py").write_text("def b():\n    pass\n", encoding="utf-8")
    repo = RepoMap(str(temp_dir))
    result = repo.get_repo_map(max_tokens=1000)
    assert "ref_repo" not in result
    assert "data" not in result
    assert repo.get_file_count() == 1


def test_git_aware_includes_untracked_nonignored_files(temp_dir):
    _init_git_repo(temp_dir, {"src/a.py": "def a():\n    pass\n"})
    (temp_dir / "src" / "untracked.py").write_text("def u():\n    pass\n", encoding="utf-8")
    repo = RepoMap(str(temp_dir))
    assert repo.get_file_count() == 2
    assert "untracked.py" in repo.get_repo_map(max_tokens=1000)


def test_repo_map_honors_real_token_budget(sample_workspace):
    repo = RepoMap(sample_workspace)
    tc = TokenCounter()
    for budget in (500, 1000, 200):
        result = repo.get_repo_map(max_tokens=budget)
        assert tc.count(result, "cl100k_base") <= budget


def test_repo_map_invalidates_on_file_change(sample_workspace):
    repo = RepoMap(sample_workspace)
    first = repo.get_repo_map(max_tokens=10000)
    utils = Path(sample_workspace) / "src" / "utils.py"
    utils.write_text(
        utils.read_text(encoding="utf-8") + "\ndef brand_new():\n pass\n", encoding="utf-8"
    )
    second = repo.get_repo_map(max_tokens=10000, force_refresh=True)
    assert first != second
    assert "brand_new" in second


def test_auto_repo_map_budget_scales_with_context():
    """An eighth of the window, floored and capped.

    Scales because the map's value is symbol density and its cost is paid from
    the same window; floored so a small-window model still gets orientation at
    all; capped because past a few thousand tokens the tree stops adding
    information and only costs prefix-cache for a map nothing reads to the end.
    """
    from server.config.constants.context import REPO_MAP_MAX_TOKENS, REPO_MAP_MIN_TOKENS

    config = _make_config(
        Path("."), max_context_tokens=DEFAULT_CONTEXT_WINDOW, repo_map_tokens=None
    )
    assert ContextManager(config)._resolve_repo_map_tokens("test-model") == REPO_MAP_MAX_TOKENS

    config = _make_config(Path("."), max_context_tokens=8000, repo_map_tokens=None)
    assert ContextManager(config)._resolve_repo_map_tokens("test-model") == REPO_MAP_MIN_TOKENS

    config = _make_config(Path("."), max_context_tokens=32_000, repo_map_tokens=None)
    assert ContextManager(config)._resolve_repo_map_tokens("test-model") == 4000


def test_explicit_repo_map_budget_overrides_the_derived_one(sample_workspace):
    config = _make_config(sample_workspace, repo_map_tokens=77)
    cm = ContextManager(config)
    assert cm._resolve_repo_map_tokens("test-model") == 77


def test_build_messages_skips_map_when_explicit_empty(sample_workspace):
    config = _make_config(sample_workspace)
    cm = ContextManager(config)
    messages = cm.build_messages(
        history=[], system_prompt="SYS", new_prompt="hi", model="test-model", repo_map=""
    )
    assert all("<repo_map>" not in m["content"] for m in messages)


def test_match_tracked_files_handles_dotfiles_and_absolute_paths(sample_workspace):
    _write(sample_workspace, ".eslintrc.json", "{}\n")
    _write(sample_workspace, ".github/workflows/ci.yml", "name: CI\n")
    repo = RepoMap(sample_workspace)
    matched = repo._match_tracked_files([
        "./.eslintrc.json",
        ".github/workflows/ci.yml",
        str(sample_workspace / "src" / "utils.py"),
    ])
    assert ".eslintrc.json" in matched
    assert ".github/workflows/ci.yml" in matched
    assert "src/utils.py" in matched


def test_repo_map_cache_survives_a_changing_conversation(sample_workspace):
    """The cache is keyed on the budget, not on the conversation.

    Keying it on the chat files made it miss on every turn that mentioned a new
    path, which is every turn — so a cache added to avoid re-deriving the map
    never once hit, and each build_messages paid for a full render.
    """
    config = _make_config(sample_workspace)
    cm = ContextManager(config)
    cm.get_repo_map(chat_files=["src/mod_b.py"])
    first_key = cm._repo_map_cache_key
    first = cm._repo_map_cache

    second = cm.get_repo_map(chat_files=["src/mod_a.py"])

    assert cm._repo_map_cache_key == first_key
    assert second == first


def test_repo_map_cache_rerenders_when_the_budget_changes(sample_workspace, monkeypatch):
    config = _make_config(sample_workspace)
    cm = ContextManager(config)
    cm.get_repo_map(chat_files=["src/mod_b.py"])
    first_key = cm._repo_map_cache_key

    monkeypatch.setattr(ContextManager, "_resolve_repo_map_tokens", lambda self, model="": first_key * 2)
    cm.get_repo_map(chat_files=["src/mod_b.py"])

    assert cm._repo_map_cache_key == first_key * 2


def test_repo_map_cache_rerenders_when_the_tree_moves(sample_workspace):
    config = _make_config(sample_workspace)
    cm = ContextManager(config)
    first = cm.get_repo_map(chat_files=[])

    _write(sample_workspace, "src/brand_new_module.py", "def appeared_late():\n    pass\n")
    second = cm.get_repo_map(chat_files=[])

    assert second != first
    assert "brand_new_module" in second


class TestMentionedSymbols:
    """The mention signal has to come from somewhere that names symbols.

    Harvesting every eight-character word out of the assistant's recent prose
    looked like the same signal and was not: "something", "component",
    "handling" all qualify, and each was worth enough boost to outrank
    structural centrality — so the map filled with whatever module happened to
    define a common noun.
    """

    @staticmethod
    def _manager():
        return ContextManager.__new__(ContextManager)

    def test_ordinary_prose_yields_no_symbols(self):
        history = [
            Message(
                session_id="s1",
                role="assistant",
                content=(
                    "I will inspect something important and different behaviour in "
                    "message handling. The component was already resolved."
                ),
            )
        ]
        assert self._manager()._mentioned_symbols(history) == set()

    def test_a_tool_call_naming_a_symbol_does(self):
        from server.domain.message import ToolCall

        history = [
            Message(
                session_id="s1",
                role="assistant",
                content="",
                tool_calls=[ToolCall(name="grep", arguments={"pattern": "build_request"})],
            )
        ]
        assert self._manager()._mentioned_symbols(history) == {"build_request"}

    def test_the_openai_wire_shape_also_works(self):
        """Persisted turns may carry the raw provider shape instead."""
        from server.agents.context import _call_arguments

        assert _call_arguments(
            {"function": {"name": "grep", "arguments": '{"pattern":"build_request"}'}}
        ) == {"pattern": "build_request"}
        assert _call_arguments({"params": {"path": "a.py"}}) == {"path": "a.py"}

    def test_only_symbol_shaped_arguments_count(self):
        """A path argument is not a symbol reference."""
        from server.domain.message import ToolCall

        history = [
            Message(
                session_id="s1",
                role="assistant",
                content="",
                tool_calls=[ToolCall(name="file_read", arguments={"path": "server/agents/context.py"})],
            )
        ]
        assert self._manager()._mentioned_symbols(history) == set()

    def test_a_malformed_call_does_not_raise(self):
        from server.agents.context import _call_arguments

        assert _call_arguments({"name": "grep", "arguments": "not json at all"}) == {}
        assert _call_arguments("not a call") == {}
        assert _call_arguments(None) == {}

    def test_a_mention_nudges_rather_than_decides(self):
        """One mentioned symbol must not leapfrog real centrality."""
        from server.workspace.repo_map import MENTIONED_SYMBOL_BOOST

        assert MENTIONED_SYMBOL_BOOST < 5.0

