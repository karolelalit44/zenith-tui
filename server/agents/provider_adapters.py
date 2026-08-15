from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    FLAGSHIP = "flagship"
    REASONING = "reasoning"
    COMPACT = "compact"


def detect_model_tier(
    model_name: str, provider_name: str = "", catalog: dict | None = None
) -> ModelTier:
    if catalog is None:
        try:
            from server.persistence.repositories import load_catalog

            catalog = load_catalog()
        except Exception:
            logger.warning(
                "Failed to load model catalog; defaulting to FLAGSHIP tier for %s", model_name
            )
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
        return (
            "<compact_model_rules>\n"
            "Compact model: no chat preambles; emit tool calls or a concise answer (<4 lines). "
            "file_read the tool reference file (path in <tool_reference>) and obey its "
            "'Compact model rules' section before acting.\n"
            "</compact_model_rules>\n"
        )
    elif tier == ModelTier.REASONING:
        return (
            "<reasoning_model_rules>\n"
            "CRITICAL INSTRUCTIONS FOR REASONING MODELS:\n"
            "1. Output your thought process inside reasoning blocks if supported by your API.\n"
            "2. ALWAYS output your complete final answer, plan, or user response in the message "
            "content body payload outside thinking blocks.\n"
            "3. Never call a tool twice with identical parameters in one turn. When complete, "
            "output your final summary text and stop.\n"
            "</reasoning_model_rules>\n"
        )
    else:
        return (
            "<flagship_model_rules>\n"
            "ANTI-LOOP RULES:\n"
            "1. Never call a tool twice with identical parameters in one turn. If you must retry, "
            "change the parameters or explain why.\n"
            "2. When the task is complete, output your final summary text and stop - do not emit "
            "tool calls.\n"
            "</flagship_model_rules>\n"
        )
