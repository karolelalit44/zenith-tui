"""LLM Provider — universal backend via LiteLLM.

Replaces per-model adapters with a single LiteLLM call that handles
all providers (NVIDIA, Groq, Gemini, OpenAI, Anthropic, etc.) uniformly.
Config-driven: litellm_prefix and api_key env var read from provider_catalog.json.

Implements both BaseProvider (backward compat) and ProviderService (typed).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import AsyncIterator

from server.domain.domain import FinishReason
from server.domain.errors import AuthenticationError, ProviderError, RateLimitError, TimeoutError
from server.persistence.repositories import load_catalog

from .base import (
    BaseProvider,
    ModelInfo,
    ProviderChunk,
    ProviderResponse,
    TokenUsage,
    ToolCall,
    ToolCallDelta,
)
from .retry import retry_with_backoff
from .token_counter import TokenCounter

logger = logging.getLogger(__name__)

_catalog: dict | None = None


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return _ANSI_RE.sub("", text)


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
    "openai_compatible": "OPENAI_API_KEY",
    "tokenrouter": "TOKENROUTER_API_KEY",
    "custom": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}



def _to_litellm_model(prefix: str, model_id: str) -> str:
    """Convert a model ID to LiteLLM format using catalog-driven prefix."""
    if not prefix:
        return model_id
    if model_id.startswith(prefix):
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
    """Extract a clean error message from litellm/provider exceptions."""
    raw = _strip_ansi(str(exc))
    try:
        json_start = raw.find('{"error"')
        if json_start >= 0:
            json_body = json.loads(raw[json_start:])
            inner_msg = json_body.get("error", {}).get("message", "")
            if inner_msg:
                return inner_msg
    except Exception:
        pass
    for prefix in ("GroqException - ", "NVIDIAException - ", "OpenAIException - ", "AnthropicException - "):
        idx = raw.rfind(prefix)
        if idx >= 0:
            return raw[idx + len(prefix):]
    if "LiteLLM" in raw or "litellm" in raw:
        parts = raw.split(": ", 2)
        if len(parts) >= 3:
            return parts[2]
    return raw


def _extract_retry_after(exc: Exception) -> float | None:
    """Extract Retry-After header from an exception's response."""
    resp = getattr(exc, "response", None)
    if resp is None:
        return None
    headers = getattr(resp, "headers", None)
    if headers is None:
        return None
    ra = headers.get("retry-after")
    if ra is None:
        return None
    try:
        return float(ra)
    except (ValueError, TypeError):
        return None


def _classify_provider_error(exc: Exception, provider_name: str) -> ProviderError:
    """Classify a provider exception using litellm's type hierarchy first, then string fallback."""
    msg = _strip_ansi(str(exc)).lower()
    clean = _extract_clean_message(exc)
    retry_after = _extract_retry_after(exc)

    # Detect unrecoverable quota / daily limit exhaustion
    is_quota_exhausted = any(q in msg for q in (
        "free-models-per-day", "insufficient_quota", "credit_balance", "payment_required", "quota_exceeded", "add 10 credits"
    ))

    # Try litellm's exception hierarchy first
    try:
        import litellm
        if isinstance(exc, litellm.ContextWindowExceededError):
            return ProviderError(
                f"Context window exceeded for provider '{provider_name}': {clean}",
                provider=provider_name, code="CONTEXT_EXCEEDED", recoverable=True,
            )
        if isinstance(exc, litellm.RateLimitError):
            return RateLimitError(
                f"Rate limited by provider '{provider_name}': {clean}",
                provider=provider_name, retry_after=retry_after, recoverable=not is_quota_exhausted,
            )
        if isinstance(exc, litellm.AuthenticationError):
            return AuthenticationError(
                f"Authentication failed for provider '{provider_name}': {clean}\nTip: Check your API key is set correctly in settings.",
                provider=provider_name,
            )
        if isinstance(exc, litellm.BadRequestError):
            if "context" in msg or "token" in msg or "length" in msg:
                return ProviderError(clean, provider=provider_name, code="CONTEXT_EXCEEDED", recoverable=True)
            return ProviderError(clean, provider=provider_name, code="BAD_REQUEST")
        if isinstance(exc, litellm.APITimeoutError):
            return TimeoutError(f"Timeout from provider '{provider_name}': {clean}", provider=provider_name)
        if isinstance(exc, litellm.APIError):
            return ProviderError(clean, provider=provider_name, code="API_ERROR", recoverable=True)
    except (ImportError, AttributeError):
        pass

    # String-based fallback for non-litellm exceptions
    if "401" in msg or "unauthorized" in msg or "invalid api key" in msg or "authentication" in msg:
        return AuthenticationError(
            f"Authentication failed for provider '{provider_name}': {clean}\nTip: Check your API key is set correctly in settings.",
            provider=provider_name,
        )
    if "429" in msg or "rate limit" in msg:
        return RateLimitError(
            f"Rate limited by provider '{provider_name}': {clean}",
            provider=provider_name, retry_after=retry_after, recoverable=not is_quota_exhausted,
        )
    if "timeout" in msg or "timed out" in msg:
        return TimeoutError(f"Timeout from provider '{provider_name}': {clean}", provider=provider_name)
    if "context_window" in msg or "context window" in msg or "maximum context" in msg or "too many tokens" in msg:
        return ProviderError(
            f"Context window exceeded for provider '{provider_name}': {clean}",
            provider=provider_name, code="CONTEXT_EXCEEDED", recoverable=True,
        )
    return ProviderError(clean, provider=provider_name)


def _extract_openrouter_cost(response) -> float | None:
    """Extract actual cost from OpenRouter response headers."""
    try:
        hp = getattr(response, "_hidden_params", None) or {}
        headers = hp.get("additional_headers", {}) or {}
        cost_str = headers.get("x-openrouter-cost") or ""
        if cost_str:
            return float(cost_str)
    except (AttributeError, TypeError, ValueError):
        pass
    try:
        headers = getattr(response, "response_headers", None) or {}
        cost_str = headers.get("x-openrouter-cost") or ""
        if cost_str:
            return float(cost_str)
    except (AttributeError, TypeError, ValueError):
        pass
    return None


def _map_finish_reason(raw: str | None) -> FinishReason:
    """Map LiteLLM finish reason string to FinishReason enum."""
    if not raw:
        return FinishReason.STOP
    mapping = {
        "stop": FinishReason.STOP,
        "length": FinishReason.LENGTH,
        "tool_calls": FinishReason.TOOL_CALLS,
        "content_filter": FinishReason.CONTENT_FILTER,
        "function_call": FinishReason.TOOL_CALLS,
    }
    return mapping.get(raw.lower(), FinishReason.STOP)


def _get_model_config(name: str, model_id: str) -> dict:
    """Resolve per-model configuration from provider_catalog.json."""
    try:
        catalog = _get_catalog()
        provider_entry = catalog["providers"].get(name, {})
        for m in provider_entry.get("models", []):
            if m["id"] == model_id:
                caps = m.get("model_capabilities", {})
                ctx = m.get("context_window", 128000)
                return {
                    "context_window": ctx,
                    "max_output_tokens": m.get("max_output_tokens", min(ctx // 4, 32768)),
                    "default_temperature": m.get("default_temperature", 0.0 if caps.get("reasoning") else 0.7),
                    "enable_thinking": caps.get("thinking", False),
                    "supports_tools": caps.get("function_calling", True),
                    "use_system_prompt": m.get("use_system_prompt", True),
                    "streaming": m.get("streaming", True),
                    "extra_params": m.get("extra_params", None),
                    "edit_format": m.get("edit_format", "tool" if caps.get("function_calling") else "diff"),
                }
    except Exception:
        pass
    return {
        "context_window": 128000,
        "max_output_tokens": 4096,
        "default_temperature": 0.7,
        "enable_thinking": False,
        "supports_tools": True,
        "use_system_prompt": True,
        "streaming": True,
        "extra_params": None,
        "edit_format": "tool",
    }


class LLMProvider(BaseProvider):
    """Universal LLM provider backed by LiteLLM.

    Implements both BaseProvider (backward compat) and ProviderService (typed).
    One code path for all providers. Config-driven via provider_catalog.json.
    """

    def __init__(
        self,
        name: str,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        enable_thinking: bool | None = None,
        reasoning_budget: int | None = None,
        extra_params: dict | None = None,
        use_system_prompt: bool | None = None,
        streaming: bool | None = None,
        weak_model: str | None = None,
    ):
        catalog = _get_catalog()
        provider_entry = catalog["providers"].get(name, {})
        resolved_model = model or provider_entry.get("default_model")
        if not resolved_model:
            raise ValueError(
                f"No model specified and no default_model in catalog for provider '{name}'. "
                f"Provide a model explicitly or add one to provider_catalog.json."
            )
        model_cfg = _get_model_config(name, resolved_model)
        resolved_max_tokens = max_tokens if max_tokens is not None else model_cfg["max_output_tokens"]
        resolved_temperature = temperature if temperature is not None else model_cfg["default_temperature"]
        super().__init__(name, resolved_model, resolved_max_tokens, resolved_temperature)
        self.api_key = api_key.strip() if api_key else None
        self.base_url = base_url.strip() if base_url else None
        self.enable_thinking = enable_thinking if enable_thinking is not None else model_cfg["enable_thinking"]
        self.reasoning_budget = reasoning_budget
        self.extra_params = extra_params if extra_params is not None else model_cfg.get("extra_params")
        self.use_system_prompt = use_system_prompt if use_system_prompt is not None else model_cfg.get("use_system_prompt", True)
        self.streaming_enabled = streaming if streaming is not None else model_cfg.get("streaming", True)
        self.edit_format = model_cfg.get("edit_format", "tool")
        self.weak_model = weak_model
        self._model_config = model_cfg
        self._last_native_tool_calls: list[dict] = []
        self._last_usage: dict = {}
        self._cumulative_usage: dict = {}
        self._last_finish_reason: FinishReason = FinishReason.STOP
        self._token_counter = TokenCounter()

        # Set API key for LiteLLM
        _set_api_key(name, self.api_key)

        # Auto-drop unsupported params (global by default, per-model exclusion available via extra_params)
        import litellm
        litellm.drop_params = True

        # Log litellm success/failure callbacks
        def _litellm_success(model, messages, response, **kwargs):
            logger.info("LITELLM SUCCESS model=%s provider=%s", self._litellm_model, name)

        def _litellm_failure(model, messages, original_exception, **kwargs):
            logger.error("LITELLM FAILURE model=%s provider=%s error=%s", self._litellm_model, name, str(original_exception)[:500])

        litellm.success_callback = [_litellm_success] if not litellm.success_callback else [*litellm.success_callback, _litellm_success]
        litellm.failure_callback = [_litellm_failure] if not litellm.failure_callback else [*litellm.failure_callback, _litellm_failure]

        # Read litellm_prefix from catalog
        litellm_prefix = provider_entry.get("litellm_prefix", "")
        if not litellm_prefix and (name in ("tokenrouter", "custom", "openai_compatible", "openai-compatible") or self.base_url):
            litellm_prefix = "openai/"

        self._litellm_prefix = litellm_prefix
        self._litellm_model = _to_litellm_model(litellm_prefix, self.model)

        # Resolve base URL from catalog if not provided
        if not self.base_url:
            self.base_url = provider_entry.get("base_url")

        if self.base_url:
            self.base_url = self.base_url.strip().rstrip("/")
            if "tokenrouter.co" in self.base_url and "tokenrouter.com" not in self.base_url:
                self.base_url = self.base_url.replace("tokenrouter.co", "tokenrouter.com")
            if self.base_url.endswith("tokenrouter.com"):
                self.base_url += "/v1"

        logger.info(
            "LLMProvider init: name=%s model=%s litellm_model=%s max_tokens=%d temperature=%.2f "
            "use_system_prompt=%s streaming=%s edit_format=%s extra_params=%s",
            name, self.model, self._litellm_model, self.max_tokens, self.temperature,
            self.use_system_prompt, self.streaming_enabled, self.edit_format,
            self.extra_params is not None,
        )

    def _build_completion_kwargs(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = False,
        tool_choice: str | None = None,
        response_format: dict | None = None,
        model_override: str | None = None,
    ) -> dict:
        """Build kwargs for litellm.acompletion().

        Merges base params with per-model extra_params from catalog (Aider-style).
        extra_params in catalog can override any param (temperature, max_tokens, etc.)
        and provides per-model flexibility without code changes.

        ``model_override`` (used for Aider-style weak-model summaries) picks a
        different model on the same provider without mutating this instance.
        """
        litellm_model = self._litellm_model
        if model_override and model_override != self.model:
            litellm_model = _to_litellm_model(self._litellm_prefix, model_override)

        kwargs: dict = {
            "model": litellm_model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": stream and self.streaming_enabled,
            "num_retries": 1,
        }
        if stream and self.streaming_enabled:
            kwargs["stream_options"] = {"include_usage": True}


        if self.base_url and not self._litellm_model.startswith("gemini/"):
            kwargs["api_base"] = self.base_url

        if self.api_key:
            kwargs["api_key"] = self.api_key

        if tools and self._model_config.get("supports_tools", True):
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"

        if response_format:
            kwargs["response_format"] = response_format

        # Per-model thinking/reasoning for Anthropic
        if self.enable_thinking and ('anthropic' in self.name.lower() or 'claude' in self._litellm_model):
            thinking_cfg: dict = {"type": "enabled"}
            if self.reasoning_budget is not None:
                thinking_cfg["budget_tokens"] = self.reasoning_budget
            kwargs["thinking"] = thinking_cfg

        # Per-model extra_params (Aider-style — merged last so they override defaults)
        if self.extra_params and isinstance(self.extra_params, dict):
            for k, v in self.extra_params.items():
                if k not in ("api_key", "api_base", "model", "messages"):
                    kwargs[k] = v

        return kwargs

    # -----------------------------------------------------------------------
    # BaseProvider interface (backward compatible — returns str)
    # -----------------------------------------------------------------------

    async def complete(self, messages: list[dict], tools: list[dict] | None = None, model: str | None = None) -> str:
        try:
            return await retry_with_backoff(self._complete_impl, messages, tools, model)
        except ProviderError:
            raise
        except Exception as e:
            logger.error("COMPLETE ERROR model=%s error=%s", self._litellm_model, str(e)[:500])
            raise _classify_provider_error(e, self.name) from e

    async def _complete_impl(self, messages: list[dict], tools: list[dict] | None = None, model: str | None = None) -> str:
        import litellm

        self._reset_cumulative_usage()
        kwargs = self._build_completion_kwargs(messages, tools, stream=False, model_override=model)
        safe_kwargs = {k: v for k, v in kwargs.items() if k != "api_key"}
        safe_kwargs["messages_count"] = len(messages)
        if tools:
            safe_kwargs["tools_count"] = len(tools)
        logger.info("API CALL (complete) model=%s kwargs=%s", self._litellm_model, json.dumps(safe_kwargs, default=str, ensure_ascii=False))
        t0 = time.monotonic()
        try:
            response = await litellm.acompletion(**kwargs)
            elapsed = (time.monotonic() - t0) * 1000
            content = response.choices[0].message.content or ""
            raw_finish = getattr(response.choices[0], "finish_reason", None)
            usage = getattr(response, "usage", None)
            logger.info(
                "API RESPONSE (complete) model=%s elapsed=%.0fms finish=%s content_len=%d usage=%s",
                self._litellm_model, elapsed, raw_finish, len(content),
                f"prompt={getattr(usage, 'prompt_tokens', '?')} completion={getattr(usage, 'completion_tokens', '?')}" if usage else "none",
            )
            logger.info("API RESPONSE CONTENT: %r", content)


            # Extract usage details including cache tokens
            usage = getattr(response, "usage", None)
            if usage:
                self._last_usage = {
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                    "total_tokens": getattr(usage, "total_tokens", 0) or 0,
                }
                details = getattr(usage, "prompt_tokens_details", None) or {}
                if isinstance(details, dict):
                    self._last_usage["cached_tokens"] = details.get("cached_tokens", 0)
                else:
                    self._last_usage["cached_tokens"] = getattr(details, "cached_tokens", 0)
                cache_creation = getattr(usage, "cache_creation_input_tokens", None)
                if cache_creation is not None:
                    self._last_usage["cache_creation_tokens"] = cache_creation
                # OpenRouter actual cost override
                or_cost = _extract_openrouter_cost(response)
                if or_cost is not None:
                    self._last_usage["_override_cost"] = or_cost
                self._accumulate_usage(self._last_usage)

            raw_finish = getattr(response.choices[0], "finish_reason", None)
            self._last_finish_reason = _map_finish_reason(raw_finish)

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
                logger.info("API TOOL_CALLS: %s", [(tc.function.name, tc.function.arguments) for tc in tool_calls])

            return content
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            logger.error("API ERROR (complete) model=%s elapsed=%.0fms error=%s", self._litellm_model, elapsed, str(e))
            raise

    def _reset_cumulative_usage(self) -> None:
        self._cumulative_usage = {}

    def _accumulate_usage(self, usage: dict) -> None:
        for k in ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens", "cache_creation_tokens"):
            v = usage.get(k, 0) or 0
            self._cumulative_usage[k] = self._cumulative_usage.get(k, 0) + v

    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        response_format: dict | None = None,
    ) -> AsyncIterator[tuple[str, str | None]]:
        """Call litellm.acompletion() with stream=True."""
        try:
            async for chunk, event_type in self._stream_impl(messages, tools, tool_choice=tool_choice, response_format=response_format):
                yield chunk, event_type
        except ProviderError:
            raise
        except Exception as e:
            logger.error("STREAM ERROR model=%s error=%s", self._litellm_model, str(e))
            raise _classify_provider_error(e, self.name) from e

    async def _stream_impl(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        response_format: dict | None = None,
    ) -> AsyncIterator[tuple[str, str | None]]:
        import litellm

        kwargs = self._build_completion_kwargs(messages, tools, stream=True, tool_choice=tool_choice, response_format=response_format)
        safe_kwargs = {k: v for k, v in kwargs.items() if k != "api_key"}
        safe_kwargs["messages_count"] = len(messages)
        if tools:
            safe_kwargs["tools_count"] = len(tools)
        logger.info("API CALL (stream) model=%s kwargs=%s", self._litellm_model, json.dumps(safe_kwargs, default=str, ensure_ascii=False))
        t0 = time.monotonic()
        stream = await litellm.acompletion(**kwargs)
        logger.info("API STREAM OPENED model=%s latency=%.0fms", self._litellm_model, (time.monotonic() - t0) * 1000)

        accumulated_tool_calls: dict[int, dict] = {}
        chunk_count = 0
        content_chars = 0
        reasoning_chars = 0
        first_chunk_time: float | None = None
        stream_usage: dict | None = None

        async for chunk in stream:
            if first_chunk_time is None:
                first_chunk_time = time.monotonic()
                logger.info("API FIRST CHUNK model=%s time_to_first_chunk=%.0fms", self._litellm_model, (first_chunk_time - t0) * 1000)
            chunk_count += 1
            delta = chunk.choices[0].delta if chunk.choices else None

            # Extract usage from last chunk (litellm puts it on the final chunk)
            if hasattr(chunk, "usage") and chunk.usage:
                u = chunk.usage
                stream_usage = {
                    "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                    "total_tokens": getattr(u, "total_tokens", 0) or 0,
                }
                details = getattr(u, "prompt_tokens_details", None) or {}
                if isinstance(details, dict):
                    stream_usage["cached_tokens"] = details.get("cached_tokens", 0)
                else:
                    stream_usage["cached_tokens"] = getattr(details, "cached_tokens", 0) if hasattr(details, "cached_tokens") else 0
                cc = getattr(u, "cache_creation_input_tokens", None) or 0
                if cc:
                    stream_usage["cache_creation_tokens"] = cc

            if not delta:
                continue

            if delta.content:
                content_chars += len(delta.content)
                yield (delta.content, None)

            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                reasoning_chars += len(reasoning)
                yield ("", reasoning)

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

        elapsed = (time.monotonic() - t0) * 1000
        finish = None
        if accumulated_tool_calls:
            tool_calls = [accumulated_tool_calls[i] for i in sorted(accumulated_tool_calls.keys())]
            self._last_native_tool_calls.extend(tool_calls)
            finish = "tool_calls"
        if stream_usage:
            self._last_usage = dict(stream_usage)
            # OpenRouter cost from the stream response
            try:
                or_cost = _extract_openrouter_cost(stream)
                if or_cost is not None:
                    self._last_usage["_override_cost"] = or_cost
            except Exception:
                pass
            self._accumulate_usage(stream_usage)
        logger.info(
            "API STREAM DONE model=%s elapsed=%.0fms chunks=%d content=%d reasoning=%d tools=%d finish=%s usage=%s",
            self._litellm_model, elapsed, chunk_count, content_chars, reasoning_chars,
            len(accumulated_tool_calls), finish, stream_usage,
        )

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

    # -----------------------------------------------------------------------
    # ProviderService typed interface
    # -----------------------------------------------------------------------

    async def complete_typed(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ProviderResponse:
        """Typed completion returning ProviderResponse."""
        self._reset_cumulative_usage()
        old_temp = self.temperature
        old_max = self.max_tokens
        if temperature is not None:
            self.temperature = temperature
        if max_tokens is not None:
            self.max_tokens = max_tokens

        try:
            import litellm

            kwargs = self._build_completion_kwargs(messages, tools, stream=False)
            response = await litellm.acompletion(**kwargs)

            content = response.choices[0].message.content or ""
            raw_finish = getattr(response.choices[0], "finish_reason", None)
            finish_reason = _map_finish_reason(raw_finish)

            # Extract tool calls
            tool_calls = []
            raw_tool_calls = response.choices[0].message.tool_calls
            if raw_tool_calls:
                for tc in raw_tool_calls:
                    args = tc.function.arguments
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    tool_calls.append(ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args if isinstance(args, dict) else {},
                        raw_arguments=tc.function.arguments if isinstance(tc.function.arguments, str) else "",
                    ))

            # Extract usage
            usage = TokenUsage()
            if hasattr(response, "usage") and response.usage:
                details = getattr(response.usage, "prompt_tokens_details", None) or {}
                cached = 0
                if isinstance(details, dict):
                    cached = details.get("cached_tokens", 0)
                elif hasattr(details, "cached_tokens"):
                    cached = getattr(details, "cached_tokens", 0)
                cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
                usage = TokenUsage(
                    prompt_tokens=getattr(response.usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(response.usage, "completion_tokens", 0) or 0,
                    total_tokens=getattr(response.usage, "total_tokens", 0) or 0,
                    cached_tokens=cached,
                )
                self._last_usage = {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                    "cached_tokens": cached,
                    "cache_creation_tokens": cache_creation,
                }
                # OpenRouter actual cost override
                or_cost = _extract_openrouter_cost(response)
                if or_cost is not None:
                    self._last_usage["_override_cost"] = or_cost
                self._accumulate_usage(self._last_usage)
                self._last_finish_reason = _map_finish_reason(getattr(response.choices[0], "finish_reason", None))

            return ProviderResponse(
                content=content,
                tool_calls=tool_calls,
                usage=usage,
                finish_reason=finish_reason,
                model=self.model,
                provider=self.name,
            )
        except ProviderError:
            raise
        except Exception as e:
            raise _classify_provider_error(e, self.name) from e
        finally:
            self.temperature = old_temp
            self.max_tokens = old_max

    async def stream_typed(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        """Typed streaming returning ProviderChunk objects."""
        self._last_native_tool_calls = []
        try:
            async for chunk in self._stream_typed_impl(messages, tools):
                yield chunk
        except ProviderError:
            raise
        except Exception as e:
            raise _classify_provider_error(e, self.name) from e

    async def _stream_typed_impl(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[ProviderChunk]:
        import litellm

        kwargs = self._build_completion_kwargs(messages, tools, stream=True)
        stream = await litellm.acompletion(**kwargs)

        accumulated_tool_calls: dict[int, dict] = {}
        stream_usage: dict | None = None

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None

            # Extract usage from last chunk (litellm puts it on the final chunk)
            if hasattr(chunk, "usage") and chunk.usage:
                u = chunk.usage
                stream_usage = {
                    "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                    "total_tokens": getattr(u, "total_tokens", 0) or 0,
                }
                details = getattr(u, "prompt_tokens_details", None) or {}
                if isinstance(details, dict):
                    stream_usage["cached_tokens"] = details.get("cached_tokens", 0)
                else:
                    stream_usage["cached_tokens"] = getattr(details, "cached_tokens", 0) if hasattr(details, "cached_tokens") else 0
                cc = getattr(u, "cache_creation_input_tokens", None) or 0
                if cc:
                    stream_usage["cache_creation_tokens"] = cc

            if not delta:
                continue

            # Content
            if delta.content:
                yield ProviderChunk(delta=delta.content)

            # Reasoning/thinking
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                yield ProviderChunk(delta="", tool_call_delta=ToolCallDelta(
                    index=-1, id=None, name=None, arguments_delta=reasoning,
                ))

            # Tool call accumulation
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
                            yield ProviderChunk(tool_call_delta=ToolCallDelta(
                                index=idx,
                                name=tc_delta.function.name,
                                arguments_delta=tc_delta.function.arguments,
                            ))

            # Finish reason
            finish = None
            if hasattr(chunk.choices[0], "finish_reason") and chunk.choices[0].finish_reason:
                finish = _map_finish_reason(chunk.choices[0].finish_reason)

            if finish:
                yield ProviderChunk(finish_reason=finish)

        # Save usage from last streaming chunk
        if stream_usage:
            self._last_usage = dict(stream_usage)
            # OpenRouter cost from the stream response
            try:
                or_cost = _extract_openrouter_cost(stream)
                if or_cost is not None:
                    self._last_usage["_override_cost"] = or_cost
            except Exception:
                pass
            self._accumulate_usage(stream_usage)

        # Yield accumulated tool calls
        if accumulated_tool_calls:
            for i in sorted(accumulated_tool_calls.keys()):
                tc = accumulated_tool_calls[i]
                args = tc["function"]["arguments"]
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                self._last_native_tool_calls.append(tc)

    def list_models_typed(self) -> list[ModelInfo]:
        """Return typed model info from catalog."""
        try:
            catalog = _get_catalog()
            provider_entry = catalog["providers"].get(self.name, {})
            models = provider_entry.get("models", [])
            result = []
            for m in models:
                caps = m.get("model_capabilities", {})
                ctx = m.get("context_window", 128000)
                max_out = m.get("max_output_tokens") or min(ctx // 4, 32768)
                result.append(ModelInfo(
                    id=m["id"],
                    name=m.get("name", m["id"]),
                    provider=self.name,
                    max_tokens=max_out,
                    context_window=ctx,
                    supports_tools=caps.get("function_calling", True),
                    supports_thinking=caps.get("thinking", False),
                    supports_vision="image" in m.get("input_modalities", []) or "image" in m.get("output_modalities", []),
                    streaming=m.get("streaming", True),
                    use_system_prompt=m.get("use_system_prompt", True),
                    edit_format=m.get("edit_format", "tool" if caps.get("function_calling") else "diff"),
                ))
            return result
        except Exception as e:
            logger.warning("Could not list models from catalog for provider '%s': %s", self.name, e)
            return [ModelInfo(id=self.model, name=self.model, provider=self.name)]

    def count_tokens(self, messages: list[dict]) -> int:
        """Count tokens in messages using tiktoken."""
        return self._token_counter.count_messages(messages, self.model)
