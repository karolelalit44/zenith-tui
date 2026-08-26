"""Tests for ``.zenithignore`` support — single workspace-skip source of truth.

Covers: startup creation, matcher semantics, hot reload, discovery hiding,
mutation blocking (reported as nonexistent), and self-edit exemption.
"""

import pytest

from server.config.constants import DEFAULT_ZENITH_IGNORE_CONTENT, ZENITH_IGNORE_FILE_NAME
from server.toolkit.tools.file_delete import FileDeleteTool
from server.toolkit.tools.file_edit import FileEditTool
from server.toolkit.tools.file_read import FileReadTool
from server.toolkit.tools.file_write import FileWriteTool
from server.toolkit.tools.glob import GlobTool
from server.toolkit.tools.grep import GrepTool
from server.toolkit.tools.list_dir import ListDirTool
from server.toolkit.tools.multi_edit import MultiEditTool
from server.workspace.ignore import (
    ZenithIgnoreMatcher,
    clear_matcher_cache,
    ensure_ignore_file,
    get_matcher,
    ignore_file_path,
)


@pytest.fixture(autouse=True)
def _clean_matcher_cache():
    clear_matcher_cache()
    yield
    clear_matcher_cache()


class TestEnsureIgnoreFile:
    def test_creates_missing_file_with_template(self, temp_dir):
        path = ensure_ignore_file(temp_dir)
        assert path == temp_dir / ZENITH_IGNORE_FILE_NAME
        assert path.read_text(encoding="utf-8") == DEFAULT_ZENITH_IGNORE_CONTENT

    def test_never_overwrites_existing_file(self, temp_dir):
        target = temp_dir / ZENITH_IGNORE_FILE_NAME
        target.write_text("*.custom\n", encoding="utf-8")
        ensure_ignore_file(temp_dir)
        assert target.read_text(encoding="utf-8") == "*.custom\n"

    def test_creation_failure_is_best_effort(self, temp_dir):
        blocker = temp_dir / ZENITH_IGNORE_FILE_NAME
        blocker.mkdir()  # a directory at the target path makes write_text fail
        result = ensure_ignore_file(temp_dir)  # must not raise
        assert result == blocker


class TestMatcherSemantics:
    def test_missing_file_falls_back_to_template(self, temp_dir):
        matcher = ZenithIgnoreMatcher(temp_dir)
        assert matcher.is_ignored("node_modules/x.js")
        assert matcher.is_ignored_dir("node_modules")
        assert not matcher.is_ignored("src/app.py")

    def test_existing_file_is_used_exclusively(self, temp_dir):
        (temp_dir / ZENITH_IGNORE_FILE_NAME).write_text("*.secret\n", encoding="utf-8")
        matcher = ZenithIgnoreMatcher(temp_dir)
        assert matcher.is_ignored("keys.secret")
        assert not matcher.is_ignored("node_modules/x.js"), "template leaked into file mode"

    def test_plain_name_matches_any_depth(self, temp_dir):
        (temp_dir / ZENITH_IGNORE_FILE_NAME).write_text("vendor\n", encoding="utf-8")
        matcher = ZenithIgnoreMatcher(temp_dir)
        assert matcher.is_ignored_dir("vendor")
        assert matcher.is_ignored("a/b/vendor/lib.js")
        assert not matcher.is_ignored("vendorlike.txt")

    def test_trailing_slash_pins_directories(self, temp_dir):
        (temp_dir / ZENITH_IGNORE_FILE_NAME).write_text("build/\n", encoding="utf-8")
        matcher = ZenithIgnoreMatcher(temp_dir)
        assert matcher.is_ignored_dir("build")
        assert matcher.is_ignored("build/out.o")

    def test_anchored_pattern_only_at_root(self, temp_dir):
        (temp_dir / ZENITH_IGNORE_FILE_NAME).write_text("/dist\n", encoding="utf-8")
        matcher = ZenithIgnoreMatcher(temp_dir)
        assert matcher.is_ignored("dist/a.txt")
        assert not matcher.is_ignored("sub/dist/a.txt")

    def test_negation_re_includes(self, temp_dir):
        (temp_dir / ZENITH_IGNORE_FILE_NAME).write_text("*.log\n!keep.log\n", encoding="utf-8")
        matcher = ZenithIgnoreMatcher(temp_dir)
        assert matcher.is_ignored("app.log")
        assert not matcher.is_ignored("keep.log")

    def test_comments_and_blank_lines_skipped(self, temp_dir):
        (temp_dir / ZENITH_IGNORE_FILE_NAME).write_text(
            "# comment\n\n  \n*.tmp\n", encoding="utf-8"
        )
        matcher = ZenithIgnoreMatcher(temp_dir)
        assert matcher.is_ignored("x.tmp")
        assert not matcher.is_ignored("# comment")

    def test_windows_backslash_paths_normalized(self, temp_dir):
        (temp_dir / ZENITH_IGNORE_FILE_NAME).write_text("logs\n", encoding="utf-8")
        matcher = ZenithIgnoreMatcher(temp_dir)
        assert matcher.is_ignored("logs\\app.log")
        assert matcher.is_ignored(".\\logs\\app.log")

    def test_ignore_file_itself_always_editable(self, temp_dir):
        (temp_dir / ZENITH_IGNORE_FILE_NAME).write_text("*\n", encoding="utf-8")
        matcher = ZenithIgnoreMatcher(temp_dir)
        assert matcher.is_ignored("anything.txt")
        assert not matcher.is_ignored(ZENITH_IGNORE_FILE_NAME)

    def test_hot_reload_without_restart(self, temp_dir):
        path = temp_dir / ZENITH_IGNORE_FILE_NAME
        path.write_text("first.pattern\n", encoding="utf-8")
        matcher = get_matcher(temp_dir)
        assert matcher.is_ignored("first.pattern")

        # Different byte length guarantees the fingerprint changes even with
        # coarse filesystem mtime granularity.
        path.write_text("second.pattern!\n", encoding="utf-8")
        matcher.refresh()
        assert not matcher.is_ignored("first.pattern")
        assert matcher.is_ignored("second.pattern!")

    def test_get_matcher_caches_per_workspace(self, temp_dir):
        assert get_matcher(temp_dir) is get_matcher(temp_dir)


class TestDiscoveryHiding:
    @pytest.mark.asyncio
    async def test_glob_hides_ignored_entries(self, temp_dir):
        ensure_ignore_file(temp_dir)
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "app.py").write_text("pass")
        (temp_dir / "node_modules").mkdir()
        (temp_dir / "node_modules" / "v.js").write_text("// v")

        result = await GlobTool().execute({"pattern": "**/*"}, str(temp_dir))
        assert result.success
        files = [p.replace("\\", "/") for p in result.metadata.get("files") or []]
        assert "src/app.py" in files
        assert ".zenithignore" in files, "ignore file must remain visible/editable"
        assert not any(f.startswith("node_modules") for f in files)

    @pytest.mark.asyncio
    async def test_grep_hides_ignored_entries(self, temp_dir):
        ensure_ignore_file(temp_dir)
        (temp_dir / "app.py").write_text("needle = 1")
        (temp_dir / "debug.log").write_text("needle in log")

        result = await GrepTool().execute({"pattern": "needle"}, str(temp_dir))
        assert result.success
        assert result.metadata["count"] == 1
        assert "debug.log" not in result.output

    @pytest.mark.asyncio
    async def test_list_dir_hides_ignored_entries(self, temp_dir):
        ensure_ignore_file(temp_dir)
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "app.py").write_text("pass")
        (temp_dir / "node_modules").mkdir()
        (temp_dir / "node_modules" / "v.js").write_text("// v")
        (temp_dir / ".env").write_text("SECRET=1")

        result = await ListDirTool().execute({"path": "."}, str(temp_dir))
        assert result.success
        assert sorted(result.metadata["entries"]) == [".zenithignore", "src/"]

    @pytest.mark.asyncio
    async def test_list_dir_shows_normal_entries(self, temp_dir):
        ensure_ignore_file(temp_dir)
        (temp_dir / "src").mkdir()
        (temp_dir / "README.md").write_text("# hi")

        result = await ListDirTool().execute({"path": "."}, str(temp_dir))
        assert result.success
        assert sorted(result.metadata["entries"]) == [".zenithignore", "README.md", "src/"]


class TestMutationBlocking:
    @pytest.mark.asyncio
    async def test_write_to_ignored_path_reports_not_found(self, temp_dir):
        ensure_ignore_file(temp_dir)
        result = await FileWriteTool().execute(
            {"path": "node_modules/pkg.js", "content": "x"}, str(temp_dir)
        )
        assert not result.success
        assert result.error == "File not found: node_modules/pkg.js"
        assert not (temp_dir / "node_modules" / "pkg.js").exists()

    @pytest.mark.asyncio
    async def test_read_ignored_path_reports_not_found(self, temp_dir):
        ensure_ignore_file(temp_dir)
        (temp_dir / ".env").write_text("SECRET=1")
        result = await FileReadTool().execute({"path": ".env"}, str(temp_dir))
        assert not result.success
        assert result.error == "File not found: .env"

    @pytest.mark.asyncio
    async def test_edit_ignored_path_reports_not_found(self, temp_dir):
        ensure_ignore_file(temp_dir)
        (temp_dir / "out.log").write_text("hello")
        result = await FileEditTool().execute(
            {"path": "out.log", "old_content": "hello", "new_content": "bye"},
            str(temp_dir),
        )
        assert not result.success
        assert result.error == "File not found: out.log"
        assert (temp_dir / "out.log").read_text(encoding="utf-8") == "hello"

    @pytest.mark.asyncio
    async def test_multi_edit_ignored_path_reports_not_found(self, temp_dir):
        ensure_ignore_file(temp_dir)
        (temp_dir / "trace.log").write_text("hello")
        result = await MultiEditTool().execute(
            {
                "filepath": "trace.log",
                "edits": [{"old_content": "hello", "new_content": "bye"}],
            },
            str(temp_dir),
        )
        assert not result.success
        assert result.error == "File not found: trace.log"

    @pytest.mark.asyncio
    async def test_delete_ignored_path_reports_not_found(self, temp_dir):
        ensure_ignore_file(temp_dir)
        (temp_dir / "build").mkdir()
        (temp_dir / "build" / "blob.bin").write_text("x")
        result = await FileDeleteTool().execute({"path": "build"}, str(temp_dir))
        assert not result.success
        assert result.error == "Not found: build"
        assert (temp_dir / "build" / "blob.bin").exists()

    @pytest.mark.asyncio
    async def test_ignore_file_itself_remains_writable(self, temp_dir):
        ensure_ignore_file(temp_dir)
        result = await FileEditTool().execute(
            {
                "path": ZENITH_IGNORE_FILE_NAME,
                "old_content": DEFAULT_ZENITH_IGNORE_CONTENT.splitlines()[3],
                "new_content": "node_modules/\n",
            },
            str(temp_dir),
        )
        assert result.success, result.error


class TestStartupIntegration:
    def test_ignore_file_seeded_before_registry_build(self, temp_dir, monkeypatch):
        """_do_startup creates .zenithignore before touching providers."""
        import asyncio

        import pytest as _pytest

        from server.api import server as api_server

        class _FakeTools:
            max_bash_timeout = 5

        class _FakeConfig:
            active_provider = ""
            home_dir = str(temp_dir)
            workspace_root = str(temp_dir)
            tools = _FakeTools()

            def __init__(self) -> None:
                self.providers: dict = {}

        monkeypatch.setattr(api_server, "load_config", lambda: _FakeConfig())

        def _boom(*_a, **_k):
            raise RuntimeError("stop before provider setup")

        monkeypatch.setattr(api_server.ProviderRegistry, "from_config", staticmethod(_boom))
        with _pytest.raises(RuntimeError):
            asyncio.run(api_server._do_startup())
        assert ignore_file_path(temp_dir).exists()
