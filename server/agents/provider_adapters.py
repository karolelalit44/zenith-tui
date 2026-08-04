
from __future__ import annotations
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    FLAGSHIP = "flagship"
    REASONING = "reasoning"
    COMPACT = "compact"


def detect_model_tier(model_name: str, provider_name: str = "", catalog: dict | None = None) -> ModelTier:
    
    if catalog is None:
        try:
            from server.persistence.repositories import load_catalog

            catalog = load_catalog()
        except Exception:
            logger.debug("Failed to resolve prompt tier from catalog for %s", model_name)
            catalog = {}
    for prov in catalog.get("providers", {}).values():
        for m in prov.get("models", []):
            if m.get("id") == model_name:
                tier = (m.get("prompt_tier") or "").strip().lower()
                try:
                    return ModelTier(tier)
                except ValueError:
                    pass
                return ModelTier.FLAGSHIP
    return ModelTier.FLAGSHIP


def get_tier_prompt_enhancements(tier: ModelTier) -> str:
    if tier == ModelTier.COMPACT:
        return """\
<compact_model_rules>
CRITICAL INSTRUCTIONS FOR COMPACT MODELS:
1. NEVER output chat preambles like "Sure, I can help with that", "Here is the code", or "Based on your request".
2. Immediately emit tool calls or concise answers under 4 lines of text.
3. Match file search patterns and edit content EXACTLY as shown in examples.
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
    else:
        return ""
