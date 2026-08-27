"""Search scope & truncation layering (AGENT_RELIABILITY_PLAN P4).

Covers:
- P4.1: vendored trees listed in ``.zenithignore`` are excluded from glob/grep.
- P4.2: any unscoped pattern over-matching BROAD_PATTERN_THRESHOLD gets the
  directory summary, so structure survives result truncation.
"""

import pytest

from server.toolkit.tools.glob import GlobTool, _pattern_is_unscoped
from server.workspace.ignore import clear_matcher_cache, ensure_ignore_file


@pytest.fixture
def workspace(temp_dir):
    """A workspace with a real package tree plus an ignored vendored tree."""
    (temp_dir / "tui" / "src").mkdir(parents=True)
    (temp_dir / "tui" / "src" / "app.tsx").write_text("export {}", encoding="utf-8")
    (temp_dir / "server").mkdir()
    (temp_dir / "server" / "main.py").write_text("x = 1", encoding="utf-8")
    ref = temp_dir / "ref_repo" / "aider" / "website"
    ref.mkdir(parents=True)
    for i in range(60):
        (ref / f"page_{i}.js").write_text("console.log(1);", encoding="utf-8")
    ensure_ignore_file(temp_dir)
    clear_matcher_cache()
    yield temp_dir
    clear_matcher_cache()


def test_pattern_is_unscoped_table():
    for pattern in ("*", "**", "**/*", "**/*.ts", "**/*.{ts,tsx}"):
        assert _pattern_is_unscoped(pattern), pattern
    for pattern in ("tui/**/*", "server/**/*.py", "src/*"):
        assert not _pattern_is_unscoped(pattern), pattern


@pytest.mark.asyncio
async def test_glob_excludes_vendored_tree_by_default(workspace):
    tool = GlobTool()
    result = await tool.execute(
        {"pattern": "**/*.{js,ts,tsx,py}", "path": str(workspace)}, str(workspace)
    )
    assert result.success
    assert "ref_repo" not in result.output, "vendored reference tree leaked into results"
    files = [p.replace("\\", "/") for p in result.metadata.get("files") or []]
    assert "tui/src/app.tsx" in files
    assert "server/main.py" in files
    assert not any(f.startswith("ref_repo/") for f in files)


@pytest.mark.asyncio
async def test_glob_broad_summary_for_over_matching_patterns(workspace):
    tool = GlobTool()
    # The vendored tree is excluded; force the broad-summary path with 60
    # non-ignored bulk files instead of relying on an ignore bypass flag.
    bulk = workspace / "bulk"
    bulk.mkdir()
    for i in range(60):
        (bulk / f"page_{i}.js").write_text("console.log(1);", encoding="utf-8")

    result = await tool.execute({"pattern": "**/*.js", "path": str(workspace)}, str(workspace))
    assert result.success
    assert result.output.startswith("Directory structure overview"), result.output[:120]
    assert "[Showing 100 of" in result.output or len(result.metadata.get("files") or []) <= 100

    # A scoped pattern never gets the summary prefix.
    scoped = await tool.execute({"pattern": "bulk/**/*", "path": str(workspace)}, str(workspace))
    assert scoped.success
    assert not scoped.output.startswith("Directory structure overview")
