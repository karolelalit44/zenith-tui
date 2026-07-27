"""LLM Provider — universal backend via LiteLLM.

Replaces per-model adapters with a single LiteLLM call that handles
all providers (NVIDIA, Groq, Gemini, OpenAI, Anthropic, etc.) uniformly.
Config-driven: litellm_prefix and api_key env var read from provider_catalog.json.
"""

import json
import logging
import os
from typing import AsyncIterator

from .base import BaseProvider
from .retry import retry_with_backoff
from zenith.db.repository import load_catalog
from zenith.core.errors import ProviderError, AuthenticationError, RateLimitError, TimeoutError

logger = logging.getLogger(__name__)

_catalog: dict | None = None


def _get_catalog() -> dict:
    global _catalog
    if _catalog is None:
        _catalog = load_catalog()
    return _catalog


# API key env var mapping per provider
_PROVIDER_KEY_ENV: dict[str, str] = {
    "nvidia": "NVIDIA_API_KEY",
    "groq": "GROQ_API_KEY",
    "google": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _to_litellm_model(prefix: str, model_id: str) -> str:
    """Convert a model ID to LiteLLM format using catalog-driven prefix.

    Always prepends the prefix. LiteLLM strips one level of provider prefix,
    so for OpenRouter model ``openrouter/free`` with prefix ``openrouter/``
    the result ``openrouter/openrouter/free`` correctly resolves — LiteLLM
    strips the first ``openrouter/`` and sends ``openrouter/free`` to the API.
    """
    if not prefix:
        return model_id
    return f"{prefix}{model_id}"


def _set_api_key(provider_name: str, api_key: str | None) -> None:
    """Set the API key as an env var for LiteLLM if provided."""
    if not api_key:
        return
    env_var = _PROVIDER_KEY_ENV.get(provider_name)
    if env_var:
        os.environ[env_var] = api_key


def _extract_clean_message(exc: Exception) -> str:
    """Extract a human-readable error message from LiteLLM/provider exceptions."""
    raw = str(exc)
    # Try to extract JSON error body from LiteLLM error chains
    # Format: "litellm.XxxError: XxxError: ProviderException - {"error":{"message":"..."}}"
    try:
        json_start = raw.find('{"error"')
        if json_start >= 0:
            json_body = json.loads(raw[json_start:])
            inner_msg = json_body.get("error", {}).get("message", "")
            if inner_msg:
                return inner_msg
    except Exception:
        pass
    # Try to extract after the last provider-specific error prefix
    for prefix in ("GroqException - ", "NVIDIAException - ", "OpenAIException - ", "AnthropicException - "):
        idx = raw.rfind(prefix)
        if idx >= 0:
            return raw[idx + len(prefix):]
    # Strip LiteLLM wrapper: "litellm.XxxError: XxxError: ..."
    if "LiteLLM" in raw or "litellm" in raw:
        # Find the second colon which typically separates the wrapper from the actual message
        parts = raw.split(": ", 2)
        if len(parts) >= 3:
            return parts[2]
    return raw


def _classify_provider_error(exc: Exception, provider_name: str) -> ProviderError:
    msg = str(exc).lower()
    clean = _extract_clean_message(exc)
    if "401" in msg or "unauthorized" in msg or "invalid api key" in msg or "authentication" in msg:
        return AuthenticationError(f"Authentication failed for provider '{provider_name}': {clean}", provider=provider_name)
    if "429" in msg or "rate limit" in msg:
        retry_after = None
        if hasattr(exc, "response") and hasattr(exc.response, "headers"):
            ra = exc.response.headers.get("retry-after")
            if ra:
                try:
                    retry_after = float(ra)
                except (ValueError, TypeError):
                    pass
        return RateLimitError(f"Rate limited by provider '{provider_name}': {clean}", provider=provider_name, retry_after=retry_after)
    if "timeout" in msg or "timed out" in msg:
        return TimeoutError(f"Timeout from provider '{provider_name}': {clean}", provider=provider_name)
    return ProviderError(clean, provider=provider_name)


class LLMProvider(BaseProvider):
    """Universal LLM provider backed by LiteLLM.

    One code path for all providers. Config-driven via provider_catalog.json.
    LiteLLM handles: provider routing, system role conversion,
    native function calling, streaming, thinking/reasoning.
    """

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

        # Set API key for LiteLLM
        _set_api_key(name, self.api_key)

        # Auto-drop unsupported params (e.g. temperature for O-series reasoning models)
        import litellm
        litellm.drop_params = True

        # Read litellm_prefix from catalog (config-driven, not hardcoded)
        litellm_prefix = provider_entry.get("litellm_prefix", "")
        self._litellm_model = _to_litellm_model(litellm_prefix, self.model)

        # Resolve base URL from catalog if not provided
        if not self.base_url:
            self.base_url = provider_entry.get("base_url")

        logger.info(
            "LLMProvider init: name=%s model=%s litellm_model=%s base_url=%s",
            name, self.model, self._litellm_model, self.base_url,
        )

    def _build_completion_kwargs(self, messages: list[dict], tools: list[dict] | None = None, stream: bool = False) -> dict:
        """Build kwargs for litellm.acompletion()."""
        kwargs: dict = {
            "model": self._litellm_model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": stream,
        }

        if self.base_url and not self._litellm_model.startswith("gemini/"):
            kwargs["api_base"] = self.base_url

        if self.api_key:
            kwargs["api_key"] = self.api_key

        # Tool calling — LiteLLM handles native FC for all providers
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        return kwargs

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> str:
        try:
            return await retry_with_backoff(self._complete_impl, messages, tools)
        except ProviderError:
            raise
        except Exception as e:
            raise _classify_provider_error(e, self.name) from e

    async def _complete_impl(self, messages: list[dict], tools: list[dict] | None = None) -> str:
        import litellm

        kwargs = self._build_completion_kwargs(messages, tools, stream=False)
        response = await litellm.acompletion(**kwargs)

        # Extract content
        content = response.choices[0].message.content or ""

        # Extract native tool calls
        tool_calls = response.choices[0].message.tool_calls
        if tool_calls:
            self._last_native_tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]

        return content

    async def stream(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[tuple[str, str | None]]:
        """Stream LLM response tokens. Exceptions propagate to caller for retry handling."""
        self._last_native_tool_calls = []
        try:
            async for chunk in self._stream_impl(messages, tools):
                yield chunk
        except ProviderError:
            raise
        except Exception as e:
            raise _classify_provider_error(e, self.name) from e

    async def _stream_impl(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[tuple[str, str | None]]:
        import litellm

        kwargs = self._build_completion_kwargs(messages, tools, stream=True)
        stream = await litellm.acompletion(**kwargs)

        # Accumulate tool calls across chunks
        accumulated_tool_calls: dict[int, dict] = {}

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            # Content tokens
            if delta.content:
                yield (delta.content, None)

            # Reasoning/thinking tokens (some providers put this in reasoning_content)
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                yield ("", reasoning)

            # Native tool call accumulation
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in accumulated_tool_calls:
                        accumulated_tool_calls[idx] = {
                            "id": tc_delta.id or "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    tc = accumulated_tool_calls[idx]
                    if tc_delta.id:
                        tc["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tc["function"]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tc["function"]["arguments"] += tc_delta.function.arguments

        # Yield accumulated tool calls as a final chunk
        if accumulated_tool_calls:
            tool_calls = [accumulated_tool_calls[i] for i in sorted(accumulated_tool_calls.keys())]
            self._last_native_tool_calls.extend(tool_calls)

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
