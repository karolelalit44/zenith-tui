import logging
from typing import AsyncIterator

from .base import BaseProvider
from .adapters import get_adapter
from .retry import retry_with_backoff, retry_stream
from zenith.db.repository import load_catalog
from zenith.core.errors import ProviderError, AuthenticationError, RateLimitError, TimeoutError

logger = logging.getLogger(__name__)

_catalog: dict | None = None


def _get_catalog() -> dict:
    global _catalog
    if _catalog is None:
        _catalog = load_catalog()
    return _catalog


EXTRA_HEADERS: dict[str, dict[str, str]] = {
    "openrouter": {
        "HTTP-Referer": "https://github.com/anomalyco/zenith",
        "X-Title": "Zenith AI Coding Assistant",
    },
}


def _classify_provider_error(exc: Exception, provider_name: str) -> ProviderError:
    msg = str(exc).lower()
    if "401" in msg or "unauthorized" in msg or "invalid api key" in msg or "authentication" in msg:
        return AuthenticationError(f"Authentication failed for provider '{provider_name}': {exc}", provider=provider_name)
    if "429" in msg or "rate limit" in msg:
        retry_after = None
        if hasattr(exc, "response") and hasattr(exc.response, "headers"):
            ra = exc.response.headers.get("retry-after")
            if ra:
                try:
                    retry_after = float(ra)
                except (ValueError, TypeError):
                    pass
        return RateLimitError(f"Rate limited by provider '{provider_name}': {exc}", provider=provider_name, retry_after=retry_after)
    if "timeout" in msg or "timed out" in msg:
        return TimeoutError(f"Timeout from provider '{provider_name}': {exc}", provider=provider_name)
    return ProviderError(str(exc), provider=provider_name)


class LLMProvider(BaseProvider):
    def __init__(
        self,
        name: str,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        api_key: str | None = None,
        base_url: str | None = None,
        enable_thinking: bool = False,
        reasoning_budget: int | None = None,
    ):
        catalog = _get_catalog()
        provider_entry = catalog["providers"].get(name, {})
        resolved_model = model or provider_entry.get("default_model")
        if not resolved_model:
            raise ValueError(
                f"No model specified and no default_model in catalog for provider '{name}'. "
                f"Provide a model explicitly or add one to provider_catalog.json."
            )
        super().__init__(name, resolved_model, max_tokens, temperature)
        self.api_key = api_key.strip() if api_key else None
        self.base_url = base_url.strip() if base_url else None
        self.enable_thinking = enable_thinking
        self.reasoning_budget = reasoning_budget
        self._last_native_tool_calls: list[dict] = []

    def _build_adapter(self):
        adapter_cls = get_adapter(self.name)
        catalog = _get_catalog()
        provider_entry = catalog["providers"].get(self.name, {})

        base = self.base_url or provider_entry.get("base_url") or None
        extra_headers = EXTRA_HEADERS.get(self.name)

        kwargs: dict = {
            "model": self.model,
            "api_key": self.api_key,
            "base_url": base,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        if adapter_cls.capabilities.thinking:
            kwargs["enable_thinking"] = self.enable_thinking
            kwargs["reasoning_budget"] = self.reasoning_budget
        elif extra_headers:
            kwargs["extra_headers"] = extra_headers

        try:
            return adapter_cls(**kwargs)
        except TypeError:
            kwargs.pop("enable_thinking", None)
            kwargs.pop("reasoning_budget", None)
            return adapter_cls(**kwargs)

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> str:
        try:
            return await retry_with_backoff(self._complete_impl, messages, tools)
        except ProviderError:
            raise
        except ImportError as e:
            if "litellm" in str(e):
                raise ProviderError(
                    "litellm not installed. Run: pip install 'zenith[llm]'",
                    provider=self.name,
                    recoverable=False,
                ) from e
            raise _classify_provider_error(e, self.name) from e
        except Exception as e:
            raise _classify_provider_error(e, self.name) from e

    async def _complete_impl(self, messages: list[dict], tools: list[dict] | None = None) -> str:
        adapter = self._build_adapter()
        return await adapter.complete(messages, tools=tools)

    async def stream(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[tuple[str, str | None]]:
        self._last_native_tool_calls = []
        try:
            async for chunk in retry_stream(
                self._stream_impl, messages, tools
            ):
                yield chunk
        except ProviderError:
            raise
        except ImportError as e:
            if "litellm" in str(e):
                raise ProviderError(
                    "litellm not installed. Run: pip install 'zenith[llm]'",
                    provider=self.name,
                    recoverable=False,
                ) from e
            raise _classify_provider_error(e, self.name) from e
        except Exception as e:
            raise _classify_provider_error(e, self.name) from e

    async def _stream_impl(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[tuple[str, str | None]]:
        adapter = self._build_adapter()
        async for chunk in adapter.stream(messages, tools=tools):
            reasoning = chunk.reasoning if chunk.reasoning else None
            if reasoning:
                logger.debug("Thinking content from %s: %s...", self.name, reasoning[:100])
            if chunk.tool_calls:
                self._last_native_tool_calls.extend(chunk.tool_calls)
            if chunk.content:
                yield (chunk.content, reasoning)
            elif reasoning:
                yield ("", reasoning)

    async def validate(self) -> bool:
        try:
            await self.complete([{"role": "user", "content": "Say OK"}])
            return True
        except Exception as e:
            logger.warning("Provider '%s' validate() failed: %s", self.name, e)
            return False

    async def list_models(self) -> list[str]:
        try:
            catalog = _get_catalog()
            provider_entry = catalog["providers"].get(self.name, {})
            models = provider_entry.get("models", [])
            if models:
                return [m["id"] for m in models]
        except Exception as e:
            logger.warning("Could not list models from catalog for provider '%s': %s", self.name, e)
        return [self.model]
