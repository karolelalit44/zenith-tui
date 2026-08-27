from __future__ import annotations

from pathlib import Path

import pytest

from server.toolkit.tools.glob import GlobTool
from server.toolkit.tools.grep import GrepTool
from server.workspace.ignore import clear_matcher_cache, ensure_ignore_file


@pytest.fixture
def ignored_ws(temp_dir: Path):
    """Workspace seeded with the default .zenithignore template."""
    ensure_ignore_file(temp_dir)
    clear_matcher_cache()
    return temp_dir


class TestGlobGuardrails:
    @pytest.mark.asyncio
    async def test_glob_default_excludes_ignored_directories(self, ignored_ws):
        (ignored_ws / "src").mkdir()
        (ignored_ws / "src" / "index.ts").write_text("console.log('hi')")
        (ignored_ws / "node_modules" / "pkg").mkdir(parents=True)
        (ignored_ws / "node_modules" / "pkg" / "index.js").write_text("// vendor")
        (ignored_ws / ".git" / "hooks").mkdir(parents=True)
        (ignored_ws / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh")
        (ignored_ws / ".venv" / "lib").mkdir(parents=True)
        (ignored_ws / ".venv" / "lib" / "pip.py").write_text("# pip")

        tool = GlobTool()
        result = await tool.execute({"pattern": "**/*"}, str(ignored_ws))
        assert result.success
        # src/index.ts + the .zenithignore file itself (always visible/editable)
        assert result.metadata["count"] == 2
        assert "src\\index.ts" in result.output or "src/index.ts" in result.output
        assert "node_modules" not in result.output
        assert ".git" not in result.output
        assert ".venv" not in result.output

    @pytest.mark.asyncio
    async def test_glob_default_excludes_lockfiles(self, ignored_ws):
        (ignored_ws / "src").mkdir()
        (ignored_ws / "src" / "main.py").write_text("print(1)")
        (ignored_ws / "package-lock.json").write_text("{}")
        (ignored_ws / "pnpm-lock.yaml").write_text("")
        (ignored_ws / "yarn.lock").write_text("")

        tool = GlobTool()
        result = await tool.execute({"pattern": "**/*"}, str(ignored_ws))
        assert result.success
        # src/main.py + the .zenithignore file itself (always visible/editable)
        assert result.metadata["count"] == 2
        assert "package-lock.json" not in result.output
        assert "pnpm-lock.yaml" not in result.output
        assert "yarn.lock" not in result.output

    @pytest.mark.asyncio
    async def test_glob_directory_structure_summary_on_broad_pattern(
        self, temp_dir: Path, monkeypatch
    ):
        import server.toolkit.tools.glob as glob_mod

        monkeypatch.setattr(glob_mod, "BROAD_PATTERN_THRESHOLD", 5)

        for folder in ("src", "server", "tests"):
            (temp_dir / folder).mkdir()
            for i in range(3):
                (temp_dir / folder / f"file_{i}.py").write_text("pass")
        (temp_dir / "README.md").write_text("# Readme")

        tool = GlobTool()
        result = await tool.execute({"pattern": "**/*"}, str(temp_dir))
        assert result.success
        assert "Directory structure overview" in result.output
        assert "📁 src/" in result.output
        assert "📁 server/" in result.output
        assert "📁 tests/" in result.output

    @pytest.mark.asyncio
    async def test_glob_caps_and_truncation_notice(self, temp_dir: Path, monkeypatch):
        import server.toolkit.tools.glob as glob_mod

        monkeypatch.setattr(glob_mod, "GLOB_MAX_RESULTS", 5)
        for i in range(12):
            (temp_dir / f"mod_{i}.py").write_text("pass")

        tool = GlobTool()
        result = await tool.execute({"pattern": "*.py"}, str(temp_dir))
        assert result.success
        assert result.metadata["count"] == 12
        assert result.metadata["shown"] == 5
        assert result.metadata["truncated"] is True
        assert "Showing 5 of 12 matches" in result.output


class TestGrepGuardrails:
    @pytest.mark.asyncio
    async def test_grep_default_excludes_ignored_directories_and_lockfiles(self, ignored_ws):
        (ignored_ws / "src").mkdir()
        (ignored_ws / "src" / "app.py").write_text("SECRET_KEY = 'valid'")
        (ignored_ws / "node_modules" / "pkg").mkdir(parents=True)
        (ignored_ws / "node_modules" / "pkg" / "index.js").write_text("SECRET_KEY = 'ignored'")
        (ignored_ws / ".git").mkdir()
        (ignored_ws / ".git" / "config").write_text("SECRET_KEY = 'ignored_git'")
        (ignored_ws / "package-lock.json").write_text("SECRET_KEY in lockfile")

        tool = GrepTool()
        result = await tool.execute({"pattern": "SECRET_KEY"}, str(ignored_ws))
        assert result.success
        assert result.metadata["count"] == 1
        assert "src" in result.output
        assert "node_modules" not in result.output
        assert ".git" not in result.output
        assert "package-lock.json" not in result.output

    @pytest.mark.asyncio
    async def test_grep_caps_matches_and_adds_notice(self, temp_dir: Path, monkeypatch):
        import server.toolkit.tools.grep as grep_mod

        monkeypatch.setattr(grep_mod, "GREP_MAX_RESULTS", 3)
        lines = "\n".join(f"target_token line {i}" for i in range(10))
        (temp_dir / "large.py").write_text(lines)

        tool = GrepTool()
        result = await tool.execute({"pattern": "target_token"}, str(temp_dir))
        assert result.success
        assert result.metadata["shown"] == 3
        assert result.metadata["truncated"] is True
        assert "Showing 3 of" in result.output

    @pytest.mark.asyncio
    async def test_grep_empty_pattern_returns_error(self, temp_dir: Path):
        tool = GrepTool()
        result = await tool.execute({"pattern": ""}, str(temp_dir))
        assert not result.success
        assert "Empty search pattern" in result.error
