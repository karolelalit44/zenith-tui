from server.agents.provider_adapters import (
    ModelTier,
    detect_model_tier,
    get_tier_prompt_enhancements,
)

_CATALOG = {
    "version": 2,
    "providers": {
        "anthropic": {
            "models": [
                {"id": "claude-sonnet-4-20250514", "prompt_tier": "flagship"},
                {"id": "claude-3-5-haiku-20241022", "prompt_tier": "compact"},
            ]
        },
        "openai": {
            "models": [
                {"id": "gpt-4o", "prompt_tier": "flagship"},
                {"id": "o3-mini", "prompt_tier": "reasoning"},
            ]
        },
        "nvidia": {
            "models": [{"id": "nvidia/nemotron-3-super-120b-a12b", "prompt_tier": "reasoning"}]
        },
        "groq": {"models": [{"id": "llama-3.1-8b-instant", "prompt_tier": "compact"}]},
    },
}


def test_detect_model_tier_reasoning():
    assert detect_model_tier("o3-mini", catalog=_CATALOG) == ModelTier.REASONING
    assert (
        detect_model_tier("nvidia/nemotron-3-super-120b-a12b", catalog=_CATALOG)
        == ModelTier.REASONING
    )


def test_detect_model_tier_compact():
    assert detect_model_tier("llama-3.1-8b-instant", catalog=_CATALOG) == ModelTier.COMPACT
    assert detect_model_tier("claude-3-5-haiku-20241022", catalog=_CATALOG) == ModelTier.COMPACT


def test_detect_model_tier_flagship():
    assert detect_model_tier("gpt-4o", catalog=_CATALOG) == ModelTier.FLAGSHIP
    assert detect_model_tier("claude-sonnet-4-20250514", catalog=_CATALOG) == ModelTier.FLAGSHIP


def test_detect_model_tier_unknown_defaults_to_flagship():
    assert detect_model_tier("deepseek-r1", catalog=_CATALOG) == ModelTier.FLAGSHIP
    assert detect_model_tier("qwen-2.5-7b", catalog={}) == ModelTier.FLAGSHIP
    assert detect_model_tier("some-model", catalog=None) == ModelTier.FLAGSHIP


def test_get_tier_prompt_enhancements():
    compact_rules = get_tier_prompt_enhancements(ModelTier.COMPACT)
    assert "<compact_model_rules>" in compact_rules
    assert "Compact model rules" in compact_rules
    assert "no chat preambles" in compact_rules
    reasoning_rules = get_tier_prompt_enhancements(ModelTier.REASONING)
    assert "<reasoning_model_rules>" in reasoning_rules
    flagship_rules = get_tier_prompt_enhancements(ModelTier.FLAGSHIP)
    assert "<flagship_model_rules>" in flagship_rules


def test_compact_rules_live_in_reference_file():
    from server.agents.prompts import TOOL_GUIDELINES_CONTENT

    rules = get_tier_prompt_enhancements(ModelTier.COMPACT)
    assert "file_read the tool reference file" in rules
    assert "NEVER output chat preambles" in TOOL_GUIDELINES_CONTENT
    assert "Never call a tool twice with identical parameters in one turn" in TOOL_GUIDELINES_CONTENT
    assert "Never write the same file path twice in one turn" in TOOL_GUIDELINES_CONTENT
    assert "output ONLY your final summary text and stop" in TOOL_GUIDELINES_CONTENT
    assert "A tool call that already succeeded this turn will be skipped" in TOOL_GUIDELINES_CONTENT


def test_large_model_rules_include_short_anti_loop_variant():
    for tier in (ModelTier.FLAGSHIP, ModelTier.REASONING):
        rules = get_tier_prompt_enhancements(tier)
        assert "Never call a tool twice with identical parameters in one turn" in rules
        assert "final summary" in rules
