
from server.agents.prompts import build_system_prompt
from server.workspace.context import load_context_files


def _write(root, name: str, content: str) -> None:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")




class TestZenithContextFiles:
    def test_zenith_local_md_loaded_into_system_prompt(self, tmp_path):
        _write(tmp_path, "zenith.local.md", "# Zenith local instructions\nBuild things carefully.")
        prompt = build_system_prompt(workspace_root=str(tmp_path), mode="build")
        assert "<project_context>" in prompt
        assert "# Zenith local instructions" in prompt
        assert "Build things carefully." in prompt

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
        assert names[1].endswith("zenith.local.md")
        claude_idx = next((i for i, n in enumerate(names) if n.endswith("CLAUDE.md")), None)
        if claude_idx is not None:
            assert claude_idx > 1

    def test_zenith_local_md_without_project_file(self, tmp_path):
        _write(tmp_path, "zenith.local.md", "local-only")
        files = load_context_files(str(tmp_path))
        assert any("zenith.local.md" in f.path for f in files)




class TestContextFileSizeGuards:
    def test_oversized_file_is_skipped(self, tmp_path):
        _write(tmp_path, "zenith.local.md", "x" * 100_000)
        files = load_context_files(str(tmp_path))
        assert not any("zenith.local.md" in f.path for f in files)

    def test_very_long_file_is_truncated(self, tmp_path):
        _write(tmp_path, "zenith.local.md", "\n".join(f"line {i}" for i in range(600)))
        prompt = build_system_prompt(workspace_root=str(tmp_path), mode="build")
        assert "... (truncated at 500 lines)" in prompt
