
"""Model capability tiering and provider prompt adaptation engine.

Detects model capabilities and adapts system prompts so lower-capability models
(e.g., Llama 8B, Qwen 7B) get strict structure and few-shot examples, reasoning
models get explicit content extraction rules, and flagship models receive clean
high-density instructions.
"""

from __future__ import annotations

from enum import Enum
import logging
import re


logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    FLAGSHIP = "flagship"      # Claude 3.5/3.7, GPT-4o, Gemini 1.5 Pro, DeepSeek V3
    REASONING = "reasoning"    # DeepSeek R1, O1/O3-Mini, Nemotron Super
    COMPACT = "compact"        # Llama 3.1 8B, Qwen 2.5 7B, Mistral 7B, small free-tier models




_REASONING_PATTERNS = [r"\br1\b", r"\bo1\b", r"\bo3\b", r"nemotron", r"thinking", r"reasoner"]
_COMPACT_PATTERNS = [r"\b8b\b", r"\b7b\b", r"\b3b\b", r"\b1b\b", r"haiku", r"\bmini\b", r"flash", r"small", r"nano"]


def detect_model_tier(model_name: str, provider_name: str = "") -> ModelTier:
    """Classify model into capability tier for targeted prompt optimization."""
    name = (model_name + " " + provider_name).lower()

    for pat in _REASONING_PATTERNS:
        if re.search(pat, name):
            return ModelTier.REASONING

    for pat in _COMPACT_PATTERNS:
        if re.search(pat, name):
            return ModelTier.COMPACT

    return ModelTier.FLAGSHIP


def get_tier_prompt_enhancements(tier: ModelTier) -> str:
    """Return targeted prompt instructions based on model capability tier."""
    if tier == ModelTier.COMPACT:
        return """\
<compact_model_rules>
CRITICAL INSTRUCTIONS FOR COMPACT MODELS:
1. NEVER output chat preambles like "Sure, I can help with that", "Here is the code", or "Based on your request".
2. Immediately emit tool calls or concise answers under 4 lines of text.
3. Match file search patterns and edit content EXACTLY as shown in examples.
4. Read files before editing. Do not guess file content.
</compact_model_rules>
"""
    elif tier == ModelTier.REASONING:
        return """\
<reasoning_model_rules>
CRITICAL INSTRUCTIONS FOR REASONING MODELS:
1. Output your thought process inside reasoning blocks if supported by your API.
2. ALWAYS output your complete final answer, plan, or user response in the message content body payload outside thinking blocks.
3. Do NOT leave content payload blank or tiny (<30 chars) after finishing reasoning.
</reasoning_model_rules>
"""
    else:  # FLAGSHIP
        return """\
<flagship_rules>
Be precise, autonomous, and surgical. Fully implement requested features without unnecessary verbosity.
</flagship_rules>
"""
