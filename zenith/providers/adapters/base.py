from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class Chunk:
    content: str | None = None
    reasoning: str | None = None
    finish_reason: str | None = None
    tool_calls: list[dict] | None = None


@dataclass
class ModelResponse:
    content: str = ""
    reasoning: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str | None = None


@dataclass(frozen=True)
class AdapterCapabilities:
    streaming: bool = True
    thinking: bool = False
    function_calling: bool = True
    max_output_tokens: int = 4096


class ModelAdapter(ABC):
    name: str = "base"
    capabilities: AdapterCapabilities = AdapterCapabilities()

    @abstractmethod
    async def stream(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[Chunk]:
        ...

    @abstractmethod
    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> str:
        ...

    def parse_response(self, raw_content: str, raw_tool_calls: list[dict] | None = None) -> ModelResponse:
        """Dedicated provider adapter response parser producing standardized ModelResponse."""
        from zenith.providers.parser import UnifiedResponseFormatter
        clean_text, tool_calls = UnifiedResponseFormatter.process_response(raw_content, raw_tool_calls)
        return ModelResponse(content=clean_text, tool_calls=tool_calls)
