from __future__ import annotations

import json

from server.config.constants import DEFAULT_TOKENIZER_MODEL
from server.providers.token_counter import TokenCounter
from server.toolkit.registry import ToolRegistry

_counter: TokenCounter | None = None


def _get_counter() -> TokenCounter:
    global _counter
    if _counter is None:
        _counter = TokenCounter()
    return _counter


def estimate_tool_schema_tokens(
    schema: dict, description: str, model: str = DEFAULT_TOKENIZER_MODEL
) -> int:
    """Estimate the input tokens an OpenAI-style tool definition consumes for ``model``.

    This is the canonical baseline measurement for schema-token budgets: the
    serialized ``type/function/name/description/parameters`` envelope rather than
    the raw schema dict, because that is what the provider prompt actually receives.
    """
    tool = {
        "type": "function",
        "function": {
            "name": "tool",
            "description": description or "",
            "parameters": schema,
        },
    }
    text = json.dumps(tool, separators=(",", ":"), ensure_ascii=False)
    return _get_counter().count(text, model)


def measure_registry_schema_tokens(
    registry: ToolRegistry, model: str = DEFAULT_TOKENIZER_MODEL
) -> dict:
    """Return the per-tool and total schema-token baseline for a registry."""
    per_tool: dict[str, int] = {}
    total = 0
    for schema in registry.get_schemas():
        name = schema.get("name", "")
        tokens = estimate_tool_schema_tokens(
            schema.get("schema", {}), schema.get("description", ""), model
        )
        per_tool[name] = tokens
        total += tokens
    return {
        "model": model,
        "tools": per_tool,
        "total_tokens": total,
        "tool_count": len(per_tool),
    }
