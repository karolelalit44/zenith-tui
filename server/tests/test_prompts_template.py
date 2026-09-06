"""Module 15 additive interface-lock: editable template files + tagged, composable sections.

The hardcoded instruction constants are Phase-3 removals; this covers the additive template/section surface.
"""

from server.agents.prompts import (
    BUILD_MODE_INSTRUCTIONS,
    PLAN_MODE_INSTRUCTIONS,
    PromptSection,
    build_plan_system_prompt,
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
    def test_build_template_loaded(self):
        text = load_prompt_template(BUILD_MODE)
        assert "BUILD mode: EXECUTE" in text

    def test_plan_template_loaded(self):
        text = load_prompt_template(PLAN_MODE)
        assert "PLANNING ONLY" in text

    def test_templates_are_python_constants(self):
        from server.prompts import BUILD_MODE_PROMPT, PLAN_MODE_PROMPT

        assert isinstance(BUILD_MODE_PROMPT, str)
        assert isinstance(PLAN_MODE_PROMPT, str)
        assert BUILD_MODE_PROMPT == load_prompt_template(BUILD_MODE)
        assert PLAN_MODE_PROMPT == load_prompt_template(PLAN_MODE)


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
        assert {"instructions", "env", "tool_reference"} <= tags
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

    def test_tool_reference_not_nested(self, tmp_path):
        prompt = build_system_prompt(str(tmp_path))
        assert "<tool_reference>" in prompt
        assert "<tool_reference>\n<tool_reference>" not in prompt
        assert prompt.count("<tool_reference>") == 1
        assert prompt.count("</tool_reference>") == 1

    def test_plan_mode_uses_plan_instructions(self, tmp_path):
        prompt = build_system_prompt(str(tmp_path), mode=PLAN_MODE)
        assert "PLANNING ONLY" in prompt
        assert "BUILD mode" not in prompt

    def test_model_name_does_not_change_prompt(self, tmp_path):
        gemini_prompt = build_system_prompt(str(tmp_path), model_name="gemini-3.0-flash")
        gpt_prompt = build_system_prompt(str(tmp_path), model_name="gpt-4o")
        assert "SAMPLING STYLE" not in gemini_prompt
        assert "SAMPLING STYLE" not in gpt_prompt


class TestEnvSectionStaticContract:
    def test_env_section_does_not_dump_workspace_files(self, tmp_path):
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "src").mkdir()
        (tmp_path / "error.log").write_text("log")
        (tmp_path / "main.py").write_text("print('hello')")

        prompt = build_system_prompt(str(tmp_path))
        # Ensure no proactive directory dumping inside the prompt
        assert "src/" not in prompt
        assert "main.py" not in prompt
        assert "node_modules" not in prompt
        assert "<env>" in prompt
        assert str(tmp_path) in prompt

    def test_env_section_remains_identical_across_filesystem_mutations(self, tmp_path):
        prompt_before = build_system_prompt(str(tmp_path))
        (tmp_path / "new_file.py").write_text("# new")
        (tmp_path / "nested_dir").mkdir()
        prompt_after = build_system_prompt(str(tmp_path))
        # KV-cache prefix invariant: prompt must not change when files are created
        assert prompt_before == prompt_after

    def test_default_template_sections_tool_reference_not_nested(self, tmp_path):
        sections = default_template_sections(BUILD_MODE, workspace_root=str(tmp_path))
        rendered = "\n\n".join(compose_system_context(sections))
        assert "<tool_reference>" in rendered
        assert "<tool_reference>\n<tool_reference>" not in rendered
        assert rendered.count("<tool_reference>") == 1
        assert rendered.count("</tool_reference>") == 1


class TestPromptPurityAndBuildModeContract:
    def test_prompt_construction_is_side_effect_free(self, tmp_path):
        assert list(tmp_path.iterdir()) == []
        build_system_prompt(str(tmp_path), mode=BUILD_MODE)
        compose_system_context(default_template_sections(BUILD_MODE, workspace_root=str(tmp_path)))
        # Zero files (e.g. tool-guidelines.md) created in the workspace
        assert list(tmp_path.iterdir()) == []

    def test_no_phantom_tools_or_ui_commands_in_build_template(self):
        text = load_prompt_template(BUILD_MODE)
        assert "explore" not in text
        assert "/compact" not in text

    def test_on_demand_tool_guidelines_reference(self, tmp_path):
        prompt = build_system_prompt(str(tmp_path))
        assert "get_tool_definition" in prompt
        assert "discover_capabilities" in prompt
        # No absolute host path leaked inside tool_reference
        tool_ref = prompt.split("<tool_reference>")[1].split("</tool_reference>")[0]
        assert str(tmp_path) not in tool_ref

    def test_turn_contract_defined_in_build_template(self):
        text = load_prompt_template(BUILD_MODE)
        assert "CONVERSATIONAL" in text
        assert "INVESTIGATION" in text
        assert "MUTATION" in text
        assert "VALIDATION" in text

    def test_core_invariants_in_build_template(self):
        text = load_prompt_template(BUILD_MODE)
        assert "Inspect before editing" in text
        assert "smallest complete change" in text.lower()
        assert "placeholders" in text
        assert "bypass tests" in text


class TestPlanModeContract:
    def test_plan_prompt_construction_is_side_effect_free(self, tmp_path):
        assert list(tmp_path.iterdir()) == []
        build_plan_system_prompt(str(tmp_path))
        assert list(tmp_path.iterdir()) == []

    def test_no_phantom_tools_or_ui_commands_in_plan_template(self):
        text = load_prompt_template(PLAN_MODE)
        assert "explore" not in text
        assert "/compact" not in text

    def test_plan_mode_turn_contract_defined(self):
        text = load_prompt_template(PLAN_MODE)
        assert "CONVERSATIONAL" in text
        assert "INVESTIGATION" in text
        assert "PLANNING" in text
        assert "MUTATION" not in text

    def test_plan_mode_write_boundary_invariants(self):
        text = load_prompt_template(PLAN_MODE)
        assert "plan.md" in text
        assert "todo.md" in text
        assert "Planning only" in text
        assert "Inspect before planning" in text

    def test_plan_mode_on_demand_guidelines(self, tmp_path):
        prompt = build_plan_system_prompt(str(tmp_path))
        assert "get_tool_definition" in prompt
        assert "discover_capabilities" in prompt
        assert "Mode: plan" in prompt

    def test_plan_system_prompt_tags(self, tmp_path):
        prompt = build_plan_system_prompt(str(tmp_path))
        assert prompt.count("<instructions>") == 1
        assert prompt.count("</instructions>") == 1
        assert prompt.count("<env>") == 1
        assert prompt.count("</env>") == 1
        assert prompt.count("<tool_reference>") == 1
        assert prompt.count("</tool_reference>") == 1


