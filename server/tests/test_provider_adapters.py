"""Unit tests for provider_adapters module."""

from server.agents.provider_adapters import (
    ModelTier,
    detect_model_tier,
    get_tier_prompt_enhancements,
)


def test_detect_model_tier_reasoning():
    assert detect_model_tier("deepseek-r1") == ModelTier.REASONING
    assert detect_model_tier("o3-mini") == ModelTier.REASONING
    assert detect_model_tier("nemotron-3-super") == ModelTier.REASONING


def test_detect_model_tier_compact():
    assert detect_model_tier("llama-3.1-8b-instant") == ModelTier.COMPACT
    assert detect_model_tier("qwen-2.5-7b") == ModelTier.COMPACT
    assert detect_model_tier("claude-3-haiku") == ModelTier.COMPACT


def test_detect_model_tier_flagship():
    assert detect_model_tier("claude-3-7-sonnet") == ModelTier.FLAGSHIP
    assert detect_model_tier("gpt-4o") == ModelTier.FLAGSHIP
    assert detect_model_tier("gemini-1.5-pro") == ModelTier.FLAGSHIP


def test_get_tier_prompt_enhancements():
    compact_rules = get_tier_prompt_enhancements(ModelTier.COMPACT)
    assert "<compact_model_rules>" in compact_rules
    assert "NEVER output chat preambles" in compact_rules

    reasoning_rules = get_tier_prompt_enhancements(ModelTier.REASONING)
    assert "<reasoning_model_rules>" in reasoning_rules

    flagship_rules = get_tier_prompt_enhancements(ModelTier.FLAGSHIP)
    assert flagship_rules == ""
