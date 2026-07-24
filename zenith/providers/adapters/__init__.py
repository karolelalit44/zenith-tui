from .base import Chunk, ModelAdapter, ModelResponse
from .openai_compat import OpenAICompatAdapter
from .nvidia import NVIDIAAdapter

ADAPTER_MAP: dict[str, type[ModelAdapter]] = {
    "openai": OpenAICompatAdapter,
    "anthropic": OpenAICompatAdapter,
    "google": OpenAICompatAdapter,
    "groq": OpenAICompatAdapter,
    "openrouter": OpenAICompatAdapter,
    "nvidia": NVIDIAAdapter,
    "custom": OpenAICompatAdapter,
}


def get_adapter(provider_name: str) -> type[ModelAdapter]:
    cls = ADAPTER_MAP.get(provider_name)
    if cls is None:
        cls = OpenAICompatAdapter
    return cls


__all__ = [
    "Chunk", "ModelAdapter", "ModelResponse",
    "OpenAICompatAdapter", "NVIDIAAdapter",
    "get_adapter", "ADAPTER_MAP",
]
