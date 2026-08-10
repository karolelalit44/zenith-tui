from server.agents.prompts import build_system_prompt
from server.workspace.context import load_context_files


def _write(root, name: str, content: str) -> None:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


class TestZenithContextFiles:
    def test_zenith_local_md_not_loaded_into_system_prompt(self, tmp_path):
        _write(tmp_path, "zenith.local.md", "# Zenith local instructions\nBuild things carefully.")
        prompt = build_system_prompt(workspace_root=str(tmp_path), mode="build")
        assert "<project_context>" not in prompt
        assert "# Zenith local instructions" not in prompt
        assert "Build things carefully." not in prompt

    def test_zenith_md_loaded_into_system_prompt(self, tmp_path):
        _write(tmp_path, "zenith.md", "# Zenith project instructions\nRun pytest before finishing.")
        prompt = build_system_prompt(workspace_root=str(tmp_path), mode="build")
        assert "# Zenith project instructions" in prompt
        assert "Run pytest before finishing." in prompt

    def test_zenith_files_load_before_claude_md(self, tmp_path):
        _write(tmp_path, "zenith.md", "zenith-content")
        _write(tmp_path, "zenith.local.md", "zenith-local-content")
        _write(tmp_path, "CLAUDE.md", "claude-content")
        files = load_context_files(str(tmp_path))
        names = [f.path for f in files]
        assert names[0].endswith("zenith.md")
        assert not any(n.endswith("zenith.local.md") for n in names)
        claude_idx = next((i for i, n in enumerate(names) if n.endswith("CLAUDE.md")), None)
        if claude_idx is not None:
            assert claude_idx > 0

    def test_zenith_local_md_without_project_file(self, tmp_path):
        _write(tmp_path, "zenith.md", "zenith-content")
        _write(tmp_path, "zenith.local.md", "zenith-local-content")
        files = load_context_files(str(tmp_path))
        names = [f.path for f in files]
        assert len(files) == 1
        assert names[0].endswith("zenith.md")

    def test_oversized_file_is_skipped(self, tmp_path, monkeypatch):
        _write(tmp_path, "zenith.md", "x" * 100000)
        files = load_context_files(str(tmp_path))
        assert files == []

    def test_very_long_file_is_truncated(self, tmp_path, monkeypatch):
        _write(tmp_path, "zenith.md", "\n".join(f"line {i}" for i in range(600)))
        files = load_context_files(str(tmp_path))
        assert files and files[0].content
        assert "... (truncated at 500 lines)" in files[0].content

    def test_zenith_local_md_longer_than_project_file_is_not_loaded(self, tmp_path):
        _write(tmp_path, "zenith.md", "short-content")
        _write(tmp_path, "zenith.local.md", "# header\n" + "y" * 200)
        files = load_context_files(str(tmp_path))
        assert files
        assert not any(f.path.endswith("zenith.local.md") for f in files)
        assert any(f.path.endswith("zenith.md") for f in files)

    def test_project_file_and_local_override_loaded(self, tmp_path):
        _write(tmp_path, "zenith.md", "# header\n" + "y" * 500)
        _write(tmp_path, "zenith.local.md", "zenith-local-content")
        files = load_context_files(str(tmp_path))
        assert files
        assert any(f.path.endswith("zenith.md") for f in files)
        assert not any(f.path.endswith("zenith.local.md") for f in files)


class TestContextFileSizeGuards:
    def test_oversized_file_is_skipped(self, tmp_path):
        _write(tmp_path, "zenith.md", "x" * 100000)
        files = load_context_files(str(tmp_path))
        assert not any("zenith.md" in f.path for f in files)

    def test_very_long_file_is_truncated(self, tmp_path):
        _write(tmp_path, "zenith.md", "\n".join(f"line {i}" for i in range(600)))
        prompt = build_system_prompt(workspace_root=str(tmp_path), mode="build")
        assert "... (truncated at 500 lines)" in prompt
