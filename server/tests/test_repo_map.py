"""Tests for HP-3: token-budgeted ranked repo map injected into context."""

import os
import subprocess
from pathlib import Path

import pytest

from server.agents.context import ContextManager
from server.config.settings import AppSettings
from server.providers.token_counter import TokenCounter
from server.workspace.repo_map import RepoMap


def _write(workspace: Path, rel: str, content: str) -> None:
    p = workspace / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


@pytest.fixture
def sample_workspace(temp_dir):
    """A small Python workspace where utils.py defines names used by 3 files."""
    _write(temp_dir, "src/utils.py",
           "def helper_a():\n    pass\n\ndef helper_b():\n    pass\n\n"
           "def helper_c():\n    pass\n\ndef helper_d():\n    pass\n")
    _write(temp_dir, "src/main.py",
           "from utils import helper_a, helper_b, helper_c, helper_d\n\n"
           "def main():\n    return helper_a()\n")
    _write(temp_dir, "src/mod_a.py",
           "from utils import helper_b\n\ndef mod_a_fn():\n    return helper_b()\n")
    _write(temp_dir, "src/mod_b.py",
           "from utils import helper_c, helper_d\n\ndef mod_b_fn():\n    return helper_c()\n")
    _write(temp_dir, "README.md", "# Sample\n\nContent here.\n")
    return temp_dir


def _estimated_tokens(text: str) -> int:
    return len(text) // 4


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
    defaults = dict(
        db_path=str(temp_dir / "test.db"),
        workspace_root=str(temp_dir),
        max_context_tokens=128000,
        repo_map_tokens=2000,
    )
    defaults.update(overrides)
    return AppSettings(**defaults)


def test_build_messages_injects_repo_map(sample_workspace):
    config = _make_config(sample_workspace)
    cm = ContextManager(config)
    messages = cm.build_messages(
        history=[], system_prompt="SYS", new_prompt="hi", model="test-model",
        repo_map="src/main.py:\n  main (line 1)",
    )
    assert messages[0] == {"role": "system", "content": "SYS"}
    assert messages[1]["role"] == "system"
    assert "<repo_map>" in messages[1]["content"]
    assert messages[-1]["content"] == "hi"


def test_build_messages_merges_map_when_no_system_role(sample_workspace):
    config = _make_config(sample_workspace)
    cm = ContextManager(config)
    messages = cm.build_messages(
        history=[], system_prompt="SYS", new_prompt="hi", model="test-model",
        use_system_prompt=False,
        repo_map="src/utils.py:\n  helper_a (line 1)",
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
        history=[], system_prompt="SYS", new_prompt="hi", model="test-model",
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
        cm.build_messages(history=[], system_prompt="SYS", new_prompt="hi", model="test-model", repo_map=""),
        "test-model",
    )
    info_with = cm.get_token_info(
        cm.build_messages(history=[], system_prompt="SYS", new_prompt="hi", model="test-model",
                          repo_map="src/main.py:\n  main (line 1)"),
        "test-model",
    )
    assert info_with.used > info_before.used


# ── New: git-aware enumeration / real-token budget / caching ─────────────


def _init_git_repo(path: Path, files: dict[str, str]) -> None:
    """Create a real git repo at ``path`` with the given files committed."""
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
            ["git"] + list(args), cwd=str(path), check=True,
            capture_output=True, text=True, env=env,
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
    utils.write_text(utils.read_text(encoding="utf-8") + "\ndef brand_new():\n    pass\n", encoding="utf-8")
    second = repo.get_repo_map(max_tokens=10000, force_refresh=True)
    assert first != second
    assert "brand_new" in second


def test_auto_repo_map_budget_scales_with_context():
    config = _make_config(
        Path("."),
        max_context_tokens=128000,
        repo_map_tokens=None,
    )
    cm = ContextManager(config)
    # 128000/8 = 16000 -> clamped to 4096
    assert cm._resolve_repo_map_tokens("test-model") == 4096

    config = _make_config(
        Path("."),
        max_context_tokens=8000,
        repo_map_tokens=None,
    )
    cm = ContextManager(config)
    # 8000/8 = 1000 -> clamped to 1024
    assert cm._resolve_repo_map_tokens("test-model") == 1024


def test_build_messages_skips_map_when_explicit_empty(sample_workspace):
    # Plan-mode path: repo_map="" with map enabled must inject nothing.
    config = _make_config(sample_workspace)
    cm = ContextManager(config)
    messages = cm.build_messages(
        history=[], system_prompt="SYS", new_prompt="hi", model="test-model",
        repo_map="",
    )
    assert all("<repo_map>" not in m["content"] for m in messages)
