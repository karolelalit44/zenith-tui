"""Module 15 additive interface-lock: editable template files + tagged, composable sections.

The hardcoded instruction constants are Phase-3 removals; this covers the additive template/section surface.
"""

from server.agents.prompts import (
    BUILD_MODE_INSTRUCTIONS,
    PLAN_MODE_INSTRUCTIONS,
    PromptSection,
    build_system_prompt,
    compose_system_context,
    default_template_sections,
    load_prompt_template,
)
from server.config.constants import BUILD_MODE, PLAN_MODE


class TestTemplateConstantConsistency:
    """Guard against drift between the editable template files and the
    hardcoded (Phase-3-removal) instruction constants."""

    def test_build_template_matches_constant(self):
        assert load_prompt_template(BUILD_MODE) == BUILD_MODE_INSTRUCTIONS

    def test_plan_template_matches_constant(self):
        assert load_prompt_template(PLAN_MODE) == PLAN_MODE_INSTRUCTIONS

    def test_build_and_plan_templates_differ(self):
        assert load_prompt_template(BUILD_MODE) != load_prompt_template(PLAN_MODE)


class TestLoadPromptTemplate:
    def test_build_template_loaded_from_file(self):
        text = load_prompt_template(BUILD_MODE)
        assert "BUILD mode: EXECUTE" in text

    def test_plan_template_loaded_from_file(self):
        text = load_prompt_template(PLAN_MODE)
        assert "PLANNING ONLY" in text

    def test_templates_come_from_editable_file_not_code(self):
        import pathlib

        p = pathlib.Path("server/prompts/templates/build.md")
        assert p.exists()
        assert p.read_text(encoding="utf-8").strip() == load_prompt_template(BUILD_MODE)


class TestPromptSection:
    def test_render_tags_content(self):
        s = PromptSection("env", "os: windows")
        assert s.render() == "<env>\nos: windows\n</env>"

    def test_lazy_callable_content(self):
        calls = []
        s = PromptSection("mode", lambda: (calls.append(1), "build")[1])
        assert callable(s.content)
        assert s.render() == "<mode>\nbuild\n</mode>"
        assert calls == [1]

    def test_is_empty(self):
        assert PromptSection("x", "").is_empty is True
        assert PromptSection("x", "y").is_empty is False


class TestDefaultTemplateSections:
    def test_expected_tags(self, tmp_path):
        sections = default_template_sections(BUILD_MODE, workspace_root=str(tmp_path))
        tags = {s.tag for s in sections}
        assert {"instructions", "env", "tool_reference", "skills"} <= tags
        instructions = next(s for s in sections if s.tag == "instructions")
        assert "BUILD mode" in instructions.render()


class TestComposeSystemContext:
    def test_empty_sections_omitted(self):
        parts = compose_system_context([PromptSection("a", "x"), PromptSection("b", "")])
        assert parts == ["<a>\nx\n</a>"]

    def test_all_present(self):
        sections = default_template_sections(BUILD_MODE)
        parts = compose_system_context(sections)
        assert len(parts) >= 3
        assert sum(1 for p in parts if p.startswith("<instructions>")) == 1


class TestBuildSystemPrompt:
    def test_contains_instructions_and_env(self, tmp_path):
        prompt = build_system_prompt(str(tmp_path))
        assert "BUILD mode" in prompt
        assert "<env>" in prompt
        assert "<tool_reference>" in prompt

    def test_plan_mode_uses_plan_instructions(self, tmp_path):
        prompt = build_system_prompt(str(tmp_path), mode=PLAN_MODE)
        assert "PLANNING ONLY" in prompt
        assert "BUILD mode" not in prompt

    def test_skills_section_included_when_provided(self, tmp_path):
        prompt = build_system_prompt(str(tmp_path), skills_section="custom skill content")
        assert "custom skill content" in prompt
        assert "<skills>" in prompt

    def test_no_skills_section_when_empty(self, tmp_path):
        prompt = build_system_prompt(str(tmp_path), skills_section="")
        assert "<skills>" not in prompt

    def test_gemini_3_plus_appends_sampling_style(self, tmp_path):
        prompt = build_system_prompt(str(tmp_path), model_name="gemini-3.0-flash")
        assert "SAMPLING STYLE" in prompt

    def test_non_gemini_no_sampling_style(self, tmp_path):
        prompt = build_system_prompt(str(tmp_path), model_name="gpt-4o")
        assert "SAMPLING STYLE" not in prompt
