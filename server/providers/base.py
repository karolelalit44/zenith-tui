from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from pydantic import BaseModel, Field

from server.config.constants import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_LLM_MAX_TOKENS,
    DEFAULT_LLM_TEMPERATURE,
)
from server.domain.domain import FinishReason
from server.domain.message import ToolCall


class BaseProvider(ABC):
    def __init__(
        self,
        name: str,
        model: str,
        max_tokens: int = DEFAULT_LLM_MAX_TOKENS,
        temperature: float = DEFAULT_LLM_TEMPERATURE,
    ):
        self.name = name
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    @abstractmethod
    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> str: ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        response_format: dict | None = None,
    ) -> AsyncIterator[tuple[str, str | None]]:
        if False:
            yield (None, None)
        raise NotImplementedError

    @abstractmethod
    async def validate(self) -> bool: ...

    @abstractmethod
    async def list_models(self) -> list[str]: ...


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0


class ToolCallDelta(BaseModel):
    index: int = 0
    id: str | None = None
    name: str | None = None
    arguments_delta: str = ""


class ProviderResponse(BaseModel):
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    finish_reason: FinishReason = FinishReason.STOP
    cached: bool = False
    model: str = ""
    provider: str = ""


class ProviderChunk(BaseModel):
    delta: str = ""
    tool_call_delta: ToolCallDelta | None = None
    usage: TokenUsage | None = None
    finish_reason: FinishReason | None = None
    cached: bool = False


class ModelInfo(BaseModel):
    id: str
    name: str
    provider: str
    max_tokens: int = 16384
    context_window: int = DEFAULT_CONTEXT_WINDOW
    supports_tools: bool = True
    supports_thinking: bool = False
    supports_vision: bool = False
    streaming: bool = True
    use_system_prompt: bool = True
    edit_format: str = "tool"


class ModelCapabilities(BaseModel):
    """Unified, provider-agnostic model capability set (codex ``ModelInfo`` /
    opencode catalog intent).

    Downstream modules (context, thinking/reasoning, markdown render) may code
    against this contract instead of poking at raw catalog dicts. All fields
    default to safe/unset values so a missing catalog entry degrades cleanly.
    """

    thinking: bool = False
    vision: bool = False
    functions: bool = True
    reasoning_summary: bool = False
    supports_temperature: bool = True


def model_capabilities_from_catalog(
    provider_name: str, model_id: str, catalog: dict | None = None
) -> ModelCapabilities:
    """Resolve a ``ModelCapabilities`` for a model from the provider catalog.

    Purely functional and additive: unknown/missing entries fall back to the
    defaults on ``ModelCapabilities``. The catalog shape is
    ``catalog["providers"][name]["models"][...]["model_capabilities"]`` (a dict
    of capability-name -> bool), exactly as zenith's catalog already encodes
    ``thinking`` / ``supports_temperature`` / ``function_calling`` today.
    """
    if catalog is None:
        try:
            from server.storage.catalog_compat import load_catalog

            catalog = load_catalog()
        except Exception:
            catalog = {}
    caps: dict = {}
    try:
        provider_entry = catalog.get("providers", {}).get(provider_name, {}) or {}
        model = next(
            (m for m in provider_entry.get("models", []) or [] if m.get("id") == model_id), None
        )
        if model is not None:
            caps = model.get("model_capabilities", {}) or {}
    except Exception:
        pass

    _key = {
        "thinking": ("thinking",),
        "vision": ("vision", "supports_vision"),
        "functions": ("function_calling", "supports_functions", "tools"),
        "reasoning_summary": ("reasoning_summary",),
        "supports_temperature": ("supports_temperature",),
    }
    out: dict = {}
    for field_name, aliases in _key.items():
        value = None
        for alias in aliases:
            if alias in caps:
                value = caps[alias]
                break
        out[field_name] = bool(value) if value is not None else getattr(ModelCapabilities(), field_name)
    return ModelCapabilities(**out)
