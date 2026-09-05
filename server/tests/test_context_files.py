from pathlib import Path

from server import workspace
from server.agents.prompts import build_plan_system_prompt, build_system_prompt
from server.config import constants


def _write(root: Path, name: str, content: str) -> None:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


class TestNoContextFilesAppended:
    """Regression tests verifying context and instruction markdown files are never appended to prompt context."""

    def test_markdown_files_not_injected_into_build_system_prompt(self, tmp_path):
        _write(tmp_path, "zenith.md", "# Zenith project instructions\nCustom secret rule.")
        _write(tmp_path, "CLAUDE.md", "claude specific context")
        _write(tmp_path, "AGENTS.md", "agents instructions")
        _write(tmp_path, "GEMINI.md", "gemini guidelines")
        _write(tmp_path, "CRUSH.md", "crush rules")
        _write(tmp_path, ".cursorrules", "cursor rules")
        _write(tmp_path, ".clinerules", "cline rules")
        _write(tmp_path, ".github/copilot-instructions.md", "copilot instructions")

        prompt = build_system_prompt(workspace_root=str(tmp_path), mode="build")

        assert "<project_context>" not in prompt
        assert "</project_context>" not in prompt
        assert "Custom secret rule." not in prompt
        assert "claude specific context" not in prompt
        assert "agents instructions" not in prompt
        assert "gemini guidelines" not in prompt
        assert "crush rules" not in prompt
        assert "cursor rules" not in prompt
        assert "cline rules" not in prompt
        assert "copilot instructions" not in prompt

    def test_markdown_files_not_injected_into_plan_system_prompt(self, tmp_path):
        _write(tmp_path, "zenith.md", "plan instructions should not be read")
        _write(tmp_path, "CLAUDE.md", "claude instructions")

        prompt = build_plan_system_prompt(workspace_root=str(tmp_path))

        assert "<project_context>" not in prompt
        assert "plan instructions should not be read" not in prompt
        assert "claude instructions" not in prompt

    def test_parent_directory_markdown_files_not_injected(self, tmp_path):
        parent_dir = tmp_path / "parent"
        ws_dir = parent_dir / "project"
        ws_dir.mkdir(parents=True, exist_ok=True)

        _write(parent_dir, "zenith.md", "parent zenith instructions")
        _write(parent_dir, "CLAUDE.md", "parent claude instructions")

        prompt = build_system_prompt(workspace_root=str(ws_dir), mode="build")

        assert "<project_context>" not in prompt
        assert "parent zenith instructions" not in prompt
        assert "parent claude instructions" not in prompt

    def test_workspace_module_does_not_export_context_files_loaders(self):
        assert not hasattr(workspace, "ContextFile")
        assert not hasattr(workspace, "load_context_files")
        assert not hasattr(workspace, "format_context_files")

    def test_constants_do_not_contain_project_context_budget(self):
        assert not hasattr(constants, "PROJECT_CONTEXT_BUDGET_RATIO")
        assert not hasattr(constants, "PROJECT_CONTEXT_MAX_CHARS")
