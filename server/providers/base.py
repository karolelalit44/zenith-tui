from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from pydantic import BaseModel, Field

from server.config.constants import DEFAULT_CONTEXT_WINDOW
from server.domain.domain import FinishReason
from server.domain.message import ToolCall


class BaseProvider(ABC):
    def __init__(self, name: str, model: str, max_tokens: int = 4096, temperature: float = 0.7):
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
        # Async-generator contract so the ABC models yield-based stream() like
        # every concrete provider (LLMProvider, test fakes).
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
