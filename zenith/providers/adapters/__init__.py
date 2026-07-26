from .base import AdapterCapabilities, Chunk, ModelAdapter, ModelResponse
from .openai_compat import OpenAICompatAdapter
from .nvidia import NVIDIAAdapter
from .groq import GroqAdapter
from .openrouter import OpenRouterAdapter
from .gemini import GeminiAdapter

ADAPTER_CLASSES: dict[str, type[ModelAdapter]] = {
    "openai_compat": OpenAICompatAdapter,
    "nvidia": NVIDIAAdapter,
    "groq": GroqAdapter,
    "openrouter": OpenRouterAdapter,
    "gemini": GeminiAdapter,
}

_catalog_cache: dict[str, str] | None = None


def _load_adapter_map() -> dict[str, str]:
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache
    from zenith.db.repository import load_catalog
    catalog = load_catalog()
    _catalog_cache = {
        pid: p.get("adapter", "openai_compat")
        for pid, p in catalog["providers"].items()
    }
    return _catalog_cache


def get_adapter(provider_name: str) -> type[ModelAdapter]:
    adapter_map = _load_adapter_map()
    adapter_type = adapter_map.get(provider_name, "openai_compat")
    cls = ADAPTER_CLASSES.get(adapter_type)
    if cls is None:
        cls = OpenAICompatAdapter
    return cls


__all__ = [
    "AdapterCapabilities", "Chunk", "ModelAdapter", "ModelResponse",
    "OpenAICompatAdapter", "NVIDIAAdapter", "GroqAdapter", "OpenRouterAdapter", "GeminiAdapter",
    "get_adapter", "ADAPTER_CLASSES",
]
