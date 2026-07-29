"""Provider base classes — typed interfaces for LLM providers.

This module provides:
- BaseProvider: the existing interface (kept for backward compatibility)
- ProviderService: the new typed interface with structured responses
- ProviderResponse / ProviderChunk: typed response models
- TokenUsage / ToolCall / ToolCallDelta: structured data models

The new interface adds:
- Typed responses (not just str)
- Token usage tracking
- Structured tool call deltas for streaming
- Model listing with metadata
- Token counting integration
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, Field

from core.domain import FinishReason

# ---------------------------------------------------------------------------
# Existing interface (backward compatible)
# ---------------------------------------------------------------------------

class BaseProvider(ABC):
    def __init__(self, name: str, model: str, max_tokens: int = 4096, temperature: float = 0.7):
        self.name = name
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    @abstractmethod
    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> str:
        ...

    @abstractmethod
    async def stream(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[tuple[str, str | None]]:
        ...

    @abstractmethod
    async def validate(self) -> bool:
        ...

    @abstractmethod
    async def list_models(self) -> list[str]:
        ...


# ---------------------------------------------------------------------------
# New typed interface
# ---------------------------------------------------------------------------

class TokenUsage(BaseModel):
    """Token usage for a single request."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0


class ToolCall(BaseModel):
    """A structured tool call from the LLM."""
    id: str = ""
    name: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    raw_arguments: str = ""


class ToolCallDelta(BaseModel):
    """Incremental tool call data during streaming."""
    index: int = 0
    id: str | None = None
    name: str | None = None
    arguments_delta: str = ""


class ProviderResponse(BaseModel):
    """Structured response from a provider completion call."""
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    finish_reason: FinishReason = FinishReason.STOP
    cached: bool = False
    model: str = ""
    provider: str = ""


class ProviderChunk(BaseModel):
    """A single chunk from a streaming response."""
    delta: str = ""
    tool_call_delta: ToolCallDelta | None = None
    usage: TokenUsage | None = None
    finish_reason: FinishReason | None = None
    cached: bool = False


class ModelInfo(BaseModel):
    """Metadata about an available model."""
    id: str
    name: str
    provider: str
    max_tokens: int = 16384
    context_window: int = 128000
    supports_tools: bool = True
    supports_thinking: bool = False
    supports_vision: bool = False
    streaming: bool = True
    use_system_prompt: bool = True
    edit_format: str = "tool"


class ProviderService(ABC):
    """Abstract provider service interface.

    This is the new typed interface. BaseProvider is kept for backward
    compatibility with existing code that expects str returns.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def model(self) -> str:
        ...

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ProviderResponse:
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        ...

    @abstractmethod
    async def validate(self) -> bool:
        ...

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        ...

    @abstractmethod
    def count_tokens(self, messages: list[dict]) -> int:
        ...
