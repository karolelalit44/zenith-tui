from __future__ import annotations

import ast
import asyncio
import json
import logging
import os
import random
import re
import time
from collections.abc import AsyncIterator

from server.config.constants import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_MIN_REQUEST_INTERVAL,
    MIN_REQUEST_INTERVAL_ENV,
    REQUEST_THROTTLE_JITTER,
)
from server.config.env import optional_float
from server.domain.domain import FinishReason
from server.domain.errors import AuthenticationError, ProviderError, RateLimitError, TimeoutError
from server.persistence.repositories import load_catalog

from .base import BaseProvider
from .token_counter import TokenCounter

logger = logging.getLogger(__name__)
_catalog: dict | None = None
_ANSI_RE = re.compile("\\x1b\\[[0-9;]*m")
# Google's 429 body carries the advised delay as `"retryDelay": "9.788501089s"`
# inside a RetryInfo detail. Accepts "9.7s", 9.7, 9000ms, 2m, ... (both the
# bare `retryDelay:` and the JSON-quoted `"retryDelay":` forms).
_RETRY_DELAY_RE = re.compile(
    r'retryDelay\s*"?\s*[:=]\s*"?(\d+(?:\.\d+)?)\s*(ms|s|m|h)?"?', re.IGNORECASE
)
# Fallback for prose like "Please retry in 9.788501089s" at the end of the
# exception message (no retryDelay key present).
_RETRY_IN_RE = re.compile(r"\bretry\s+in\s+(\d+(?:\.\d+)?)\s*(ms|s|m|h)?\b", re.IGNORECASE)
_MIN_REQUEST_INTERVAL_DEFAULT = optional_float(
    MIN_REQUEST_INTERVAL_ENV, DEFAULT_MIN_REQUEST_INTERVAL
)
# Daily/billing quota exhaustion is terminal within a turn (recoverable=False).
# Per-minute free-tier throttling ("quota exceeded", "free_tier_requests",
# RESOURCE_EXHAUSTED, ...) is transient and stays recoverable=True with a
# server-advised cooldown (see llm_stream). Only the hard keywords below flip
# a 429 into a non-recoverable error.
_QUOTA_EXHAUSTED_KEYWORDS = (
    "free-models-per-day",
    "insufficient_quota",
    "credit_balance",
    "payment_required",
    "add 10 credits",
    "daily quota",
    "daily_limit",
)


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _get_catalog() -> dict:
    global _catalog
    if _catalog is None:
        _catalog = load_catalog()
    return _catalog


def _to_litellm_model(prefix: str, model_id: str) -> str:
    if not prefix:
        return model_id
    if model_id.startswith(prefix):
        return model_id
    return f"{prefix}{model_id}"


def _set_api_key(provider_name: str, api_key: str | None) -> None:
    if not api_key:
        return
    entry = _get_catalog().get("providers", {}).get(provider_name) or {}
    for env_var in entry.get("env_keys") or []:
        os.environ[env_var] = api_key


def _unwrap_bytes_literal(text: str) -> str:
    """Strip a ``b'...'`` / ``b"..."`` wrapper embedded in a message.

    litellm surfaces Google's JSON error body as the repr of a bytes object
    (``b'{"error": {...}}'``). Evaluating that repr with ``ast.literal_eval``
    yields the original bytes (handling ``\\n``, ``\\xNN``, ``\\u`` and quote
    escapes correctly), which is then decoded back to text so the JSON parser
    sees the actual body instead of a ``b'...'``-wrapped blob.
    """
    stripped = text.strip()
    for marker in ("b'", 'b"'):
        start = stripped.find(marker)
        if start < 0:
            continue
        quote = marker[1]
        end = stripped.rfind(quote)
        if end <= start + 2:
            continue
        try:
            payload = ast.literal_eval(stripped[start : end + 1])
        except (ValueError, SyntaxError, TypeError):
            continue
        if isinstance(payload, bytes):
            return payload.decode("utf-8", errors="replace")
    return text


def _extract_json_error_message(text: str) -> str:
    """Pull a clean message out of an embedded JSON error object.

    Scans for the first parseable JSON object anywhere in ``text`` (handles the
    surrounding litellm/provider wrapper text) and prefers ``error.message``.
    """
    decoder = json.JSONDecoder()
    idx = 0
    while True:
        idx = text.find("{", idx)
        if idx < 0:
            return ""
        try:
            obj, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            idx += 1
            continue
        if isinstance(obj, dict):
            err = obj.get("error")
            if isinstance(err, dict):
                msg = err.get("message")
                if msg:
                    return str(msg)
            msg = obj.get("message")
            if msg:
                return str(msg)
        idx = max(idx + 1, end)


def _extract_clean_message(exc: Exception) -> str:
    raw = _strip_ansi(str(exc))
    for candidate in (raw, _unwrap_bytes_literal(raw)):
        inner_msg = _extract_json_error_message(candidate)
        if inner_msg:
            return inner_msg
    for prefix in (
        "GroqException - ",
        "NVIDIAException - ",
        "OpenAIException - ",
        "AnthropicException - ",
    ):
        idx = raw.rfind(prefix)
        if idx >= 0:
            return raw[idx + len(prefix) :]
    if "LiteLLM" in raw or "litellm" in raw:
        parts = raw.split(": ", 2)
        if len(parts) >= 3:
            return parts[2]
    return raw


def _parse_retry_delay(text: str) -> float | None:
    """Parse a provider-advised retry delay out of an error body.

    Google (among others) does not set a ``retry-after`` header; it embeds the
    delay as ``"retryDelay": "9.788501089s"`` inside a ``RetryInfo`` detail in
    the JSON body, which litellm surfaces as part of ``str(exc)``. This handles
    that form plus bare seconds, milliseconds, minutes, and hours.
    """
    if not text:
        return None
    match = _RETRY_DELAY_RE.search(text) or _RETRY_IN_RE.search(text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except (TypeError, ValueError):
        return None
    unit = (match.group(2) or "").lower()
    if unit == "ms":
        return value / 1000.0
    if unit == "m":
        return value * 60.0
    if unit == "h":
        return value * 3600.0
    return value


def _extract_retry_after(exc: Exception) -> float | None:
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None) if resp is not None else None
    if headers:
        ra = headers.get("retry-after")
        if ra is not None:
            try:
                return float(ra)
            except (TypeError, ValueError):
                pass
    # The HTTP header is the common case; Google only surfaces the delay in the
    # body, so scan str(exc) and any response payload for a retryDelay hint.
    body_parts = [_strip_ansi(str(exc))]
    if resp is not None:
        for attr in ("content", "body", "text"):
            raw = getattr(resp, attr, None)
            if raw is None:
                continue
            if isinstance(raw, bytes):
                try:
                    raw = raw.decode("utf-8", errors="replace")
                except Exception:  # pragma: no cover - defensive
                    continue
            body_parts.append(str(raw))
    for text in body_parts:
        parsed = _parse_retry_delay(text)
        if parsed is not None:
            return parsed
    return None


def _classify_provider_error(exc: Exception, provider_name: str) -> ProviderError:
    msg = _strip_ansi(str(exc)).lower()
    clean = _extract_clean_message(exc)
    retry_after = _extract_retry_after(exc)
    is_quota_exhausted = any(q in msg for q in _QUOTA_EXHAUSTED_KEYWORDS)
    try:
        import litellm

        if isinstance(exc, litellm.ContextWindowExceededError):
            return ProviderError(
                f"Context window exceeded for provider '{provider_name}': {clean}",
                provider=provider_name,
                code="CONTEXT_EXCEEDED",
                recoverable=True,
            )
        if isinstance(exc, litellm.RateLimitError):
            return RateLimitError(
                f"Rate limited by provider '{provider_name}': {clean}",
                provider=provider_name,
                retry_after=retry_after,
                recoverable=not is_quota_exhausted,
            )
        if isinstance(exc, litellm.AuthenticationError):
            return AuthenticationError(
                f"Authentication failed for provider '{provider_name}': {clean}\nTip: Check your API key is set correctly in settings.",
                provider=provider_name,
            )
        if isinstance(exc, litellm.BadRequestError):
            if "context" in msg or "token" in msg or "length" in msg:
                return ProviderError(
                    clean, provider=provider_name, code="CONTEXT_EXCEEDED", recoverable=True
                )
            return ProviderError(clean, provider=provider_name, code="BAD_REQUEST")
        if isinstance(exc, litellm.APITimeoutError):
            return TimeoutError(
                f"Timeout from provider '{provider_name}': {clean}", provider=provider_name
            )
        if isinstance(exc, litellm.APIError):
            return ProviderError(clean, provider=provider_name, code="API_ERROR", recoverable=True)
    except (ImportError, AttributeError):
        pass
    if (
        "401" in msg
        or "unauthorized" in msg
        or "invalid api key" in msg
        or ("authentication" in msg)
    ):
        return AuthenticationError(
            f"Authentication failed for provider '{provider_name}': {clean}\nTip: Check your API key is set correctly in settings.",
            provider=provider_name,
        )
    if "429" in msg or "rate limit" in msg or is_quota_exhausted:
        return RateLimitError(
            f"Rate limited by provider '{provider_name}': {clean}",
            provider=provider_name,
            retry_after=retry_after,
            recoverable=not is_quota_exhausted,
        )
    if "timeout" in msg or "timed out" in msg:
        return TimeoutError(
            f"Timeout from provider '{provider_name}': {clean}", provider=provider_name
        )
    if (
        "context_window" in msg
        or "context window" in msg
        or "maximum context" in msg
        or ("too many tokens" in msg)
    ):
        return ProviderError(
            f"Context window exceeded for provider '{provider_name}': {clean}",
            provider=provider_name,
            code="CONTEXT_EXCEEDED",
            recoverable=True,
        )
    return ProviderError(clean, provider=provider_name)


def _extract_openrouter_cost(response) -> float | None:
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
    try:
        catalog = _get_catalog()
        provider_entry = catalog["providers"].get(name, {})
        for m in provider_entry.get("models", []):
            if m["id"] == model_id:
                caps = m.get("model_capabilities", {})
                ctx = m.get("context_window", DEFAULT_CONTEXT_WINDOW)
                return {
                    "context_window": ctx,
                    "max_output_tokens": m.get("max_output_tokens", min(ctx // 4, 32768)),
                    "default_temperature": m.get(
                        "default_temperature", 0.0 if caps.get("reasoning") else 0.7
                    ),
                    "supports_temperature": caps.get("supports_temperature", True),
                    "enable_thinking": caps.get("thinking", False),
                    "supports_tools": caps.get("function_calling", True),
                    "use_system_prompt": m.get("use_system_prompt", True),
                    "streaming": m.get("streaming", True),
                    "extra_params": m.get("extra_params", None),
                    "edit_format": m.get(
                        "edit_format", "tool" if caps.get("function_calling") else "diff"
                    ),
                }
    except Exception:
        pass
    return {
        "context_window": DEFAULT_CONTEXT_WINDOW,
        "max_output_tokens": 4096,
        "default_temperature": 0.7,
        "supports_temperature": True,
        "enable_thinking": False,
        "supports_tools": True,
        "use_system_prompt": True,
        "streaming": True,
        "extra_params": None,
        "edit_format": "tool",
    }


def _resolve_min_request_interval(provider_name: str) -> float:
    """Per-provider request pacing: catalog ``rate_limit`` beats the env default.

    ``ZENITH_MIN_REQUEST_INTERVAL`` is the global default (disabled unless set);
    a catalog ``rate_limit`` entry (e.g. ``{"requests_per_minute": 15}`` for
    Google AI Studio free tier) overrides it for that provider.
    """
    try:
        entry = _get_catalog().get("providers", {}).get(provider_name) or {}
        rate_limit = entry.get("rate_limit") or {}
        rpm = rate_limit.get("requests_per_minute")
        if isinstance(rpm, (int, float)) and rpm > 0:
            return 60.0 / float(rpm)
        catalog_interval = rate_limit.get("min_request_interval")
        if isinstance(catalog_interval, (int, float)) and catalog_interval >= 0:
            return float(catalog_interval)
    except Exception:
        pass
    return _MIN_REQUEST_INTERVAL_DEFAULT


class _RequestThrottle:
    """Paces independent API calls so a turn cannot outrun a provider quota.

    ``min_interval`` is the minimum wall-clock gap between call starts (~4 s
    for a 15 req/min free tier). ``wait()`` sleeps only as long as needed to
    restore that gap, plus a little jitter so bursts from concurrent sessions
    don't all land on the same second.
    """

    def __init__(self, min_interval: float, jitter: float = REQUEST_THROTTLE_JITTER):
        self.min_interval = max(0.0, min_interval)
        self.jitter = jitter
        self._last_start: float | None = None

    async def wait(self) -> float:
        """Sleep until the next call start is allowed; returns seconds waited."""
        if self.min_interval <= 0:
            return 0.0
        now = time.monotonic()
        if self._last_start is not None:
            needed = self.min_interval - (now - self._last_start)
            if needed > 0:
                delay = needed + random.uniform(0, self.jitter)
                await asyncio.sleep(delay)
                self._last_start = time.monotonic()
                return delay
        self._last_start = now
        return 0.0


class LLMProvider(BaseProvider):
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
                f"No model specified and no default_model in catalog for provider '{name}'. Provide a model explicitly or add one to the provider catalog."
            )
        model_cfg = _get_model_config(name, resolved_model)
        resolved_max_tokens = (
            max_tokens if max_tokens is not None else model_cfg["max_output_tokens"]
        )
        resolved_temperature = (
            temperature if temperature is not None else model_cfg["default_temperature"]
        )
        super().__init__(name, resolved_model, resolved_max_tokens, resolved_temperature)
        self.api_key = api_key.strip() if api_key else None
        self.base_url = base_url.strip() if base_url else None
        self.enable_thinking = (
            enable_thinking if enable_thinking is not None else model_cfg["enable_thinking"]
        )
        self.reasoning_budget = reasoning_budget
        self.extra_params = (
            extra_params if extra_params is not None else model_cfg.get("extra_params")
        )
        self.use_system_prompt = (
            use_system_prompt
            if use_system_prompt is not None
            else model_cfg.get("use_system_prompt", True)
        )
        self.streaming_enabled = (
            streaming if streaming is not None else model_cfg.get("streaming", True)
        )
        self.edit_format = model_cfg.get("edit_format", "tool")
        self.supports_temperature = model_cfg.get("supports_temperature", True)
        self.weak_model = weak_model
        self._model_config = model_cfg
        self._last_native_tool_calls: list[dict] = []
        self._last_usage: dict = {}
        self._cumulative_usage: dict = {}
        self._last_finish_reason: FinishReason = FinishReason.STOP
        self._token_counter = TokenCounter()
        self._throttle = _RequestThrottle(_resolve_min_request_interval(name))
        _set_api_key(name, self.api_key)
        import litellm

        litellm.drop_params = True

        def _litellm_success(model, messages, response, **kwargs):
            logger.info("LITELLM SUCCESS model=%s provider=%s", self._litellm_model, name)

        def _litellm_failure(model, messages, original_exception, **kwargs):
            logger.error(
                "LITELLM FAILURE model=%s provider=%s error=%s",
                self._litellm_model,
                name,
                str(original_exception)[:500],
            )

        litellm.success_callback = (
            [_litellm_success]
            if not litellm.success_callback
            else [*litellm.success_callback, _litellm_success]
        )
        litellm.failure_callback = (
            [_litellm_failure]
            if not litellm.failure_callback
            else [*litellm.failure_callback, _litellm_failure]
        )
        litellm_prefix = provider_entry.get("litellm_prefix", "")
        if not litellm_prefix and self.base_url:
            litellm_prefix = "openai/"
        self._litellm_prefix = litellm_prefix
        self._litellm_model = _to_litellm_model(litellm_prefix, self.model)
        self._base_url_style = provider_entry.get("base_url_style") or ""
        self._supports_thinking_headers = bool(
            provider_entry.get("supports_thinking_headers", False)
        )
        if not self.base_url:
            self.base_url = provider_entry.get("base_url")
        if self.base_url:
            self.base_url = self.base_url.strip().rstrip("/")
            if self._base_url_style == "tokenrouter":
                if "tokenrouter.co" in self.base_url and "tokenrouter.com" not in self.base_url:
                    self.base_url = self.base_url.replace("tokenrouter.co", "tokenrouter.com")
                if self.base_url.endswith("tokenrouter.com"):
                    self.base_url += "/v1"
        logger.info(
            "LLMProvider init: name=%s model=%s litellm_model=%s max_tokens=%d temperature=%.2f use_system_prompt=%s streaming=%s edit_format=%s extra_params=%s",
            name,
            self.model,
            self._litellm_model,
            self.max_tokens,
            self.temperature,
            self.use_system_prompt,
            self.streaming_enabled,
            self.edit_format,
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
        litellm_model = self._litellm_model
        if model_override and model_override != self.model:
            litellm_model = _to_litellm_model(self._litellm_prefix, model_override)
        kwargs: dict = {
            "model": litellm_model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "stream": stream and self.streaming_enabled,
        }
        if self.supports_temperature:
            kwargs["temperature"] = self.temperature
        if stream and self.streaming_enabled:
            kwargs["stream_options"] = {"include_usage": True}
        if self.base_url and self._base_url_style != "gemini":
            kwargs["api_base"] = self.base_url
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if tools and self._model_config.get("supports_tools", True):
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"
        if response_format:
            kwargs["response_format"] = response_format
        if self.enable_thinking and self._supports_thinking_headers:
            thinking_cfg: dict = {"type": "enabled"}
            if self.reasoning_budget is not None:
                thinking_cfg["budget_tokens"] = self.reasoning_budget
            kwargs["thinking"] = thinking_cfg
        if self.extra_params and isinstance(self.extra_params, dict):
            for k, v in self.extra_params.items():
                if k not in ("api_key", "api_base", "model", "messages"):
                    kwargs[k] = v
        return kwargs

    async def complete(
        self, messages: list[dict], tools: list[dict] | None = None, model: str | None = None
    ) -> str:
        # A single attempt: no silent retries/backoff. Provider failures are
        # classified and surfaced to the caller as explicit errors.
        try:
            return await self._complete_impl(messages, tools, model)
        except ProviderError:
            raise
        except Exception as e:
            logger.error("COMPLETE ERROR model=%s error=%s", self._litellm_model, str(e)[:500])
            raise _classify_provider_error(e, self.name) from e

    async def _complete_impl(
        self, messages: list[dict], tools: list[dict] | None = None, model: str | None = None
    ) -> str:
        import litellm

        self._reset_cumulative_usage()
        kwargs = self._build_completion_kwargs(messages, tools, stream=False, model_override=model)
        safe_kwargs = {k: v for k, v in kwargs.items() if k != "api_key"}
        safe_kwargs["messages_count"] = len(messages)
        if tools:
            safe_kwargs["tools_count"] = len(tools)
        logger.info(
            "API CALL (complete) model=%s kwargs=%s",
            self._litellm_model,
            json.dumps(safe_kwargs, default=str, ensure_ascii=False),
        )
        await self._throttle.wait()
        t0 = time.monotonic()
        try:
            response = await litellm.acompletion(**kwargs)
            elapsed = (time.monotonic() - t0) * 1000
            content = response.choices[0].message.content or ""
            raw_finish = getattr(response.choices[0], "finish_reason", None)
            usage = getattr(response, "usage", None)
            logger.info(
                "API RESPONSE (complete) model=%s elapsed=%.0fms finish=%s content_len=%d usage=%s",
                self._litellm_model,
                elapsed,
                raw_finish,
                len(content),
                f"prompt={getattr(usage, 'prompt_tokens', '?')} completion={getattr(usage, 'completion_tokens', '?')}"
                if usage
                else "none",
            )
            logger.info("API RESPONSE CONTENT: %r", content)
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
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ]
                logger.info(
                    "API TOOL_CALLS: %s",
                    [(tc.function.name, tc.function.arguments) for tc in tool_calls],
                )
            return content
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            logger.error(
                "API ERROR (complete) model=%s elapsed=%.0fms error=%s",
                self._litellm_model,
                elapsed,
                str(e),
            )
            raise

    def _reset_cumulative_usage(self) -> None:
        self._cumulative_usage = {}

    def _accumulate_usage(self, usage: dict) -> None:
        for k in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "cached_tokens",
            "cache_creation_tokens",
        ):
            v = usage.get(k, 0) or 0
            self._cumulative_usage[k] = self._cumulative_usage.get(k, 0) + v

    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        response_format: dict | None = None,
    ) -> AsyncIterator[tuple[str, str | None]]:
        try:
            async for chunk, event_type in self._stream_impl(
                messages, tools, tool_choice=tool_choice, response_format=response_format
            ):
                yield (chunk, event_type)
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

        kwargs = self._build_completion_kwargs(
            messages, tools, stream=True, tool_choice=tool_choice, response_format=response_format
        )
        safe_kwargs = {k: v for k, v in kwargs.items() if k != "api_key"}
        safe_kwargs["messages_count"] = len(messages)
        if tools:
            safe_kwargs["tools_count"] = len(tools)
        logger.info(
            "API CALL (stream) model=%s kwargs=%s",
            self._litellm_model,
            json.dumps(safe_kwargs, default=str, ensure_ascii=False),
        )
        await self._throttle.wait()
        t0 = time.monotonic()
        stream = await litellm.acompletion(**kwargs)
        logger.info(
            "API STREAM OPENED model=%s latency=%.0fms",
            self._litellm_model,
            (time.monotonic() - t0) * 1000,
        )
        accumulated_tool_calls: dict[int, dict] = {}
        chunk_count = 0
        content_chars = 0
        reasoning_chars = 0
        first_chunk_time: float | None = None
        stream_usage: dict | None = None
        async for chunk in stream:
            if first_chunk_time is None:
                first_chunk_time = time.monotonic()
                logger.info(
                    "API FIRST CHUNK model=%s time_to_first_chunk=%.0fms",
                    self._litellm_model,
                    (first_chunk_time - t0) * 1000,
                )
            chunk_count += 1
            delta = chunk.choices[0].delta if chunk.choices else None
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
                    stream_usage["cached_tokens"] = (
                        getattr(details, "cached_tokens", 0)
                        if hasattr(details, "cached_tokens")
                        else 0
                    )
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
            try:
                or_cost = _extract_openrouter_cost(stream)
                if or_cost is not None:
                    self._last_usage["_override_cost"] = or_cost
            except Exception:
                pass
            self._accumulate_usage(stream_usage)
        logger.info(
            "API STREAM DONE model=%s elapsed=%.0fms chunks=%d content=%d reasoning=%d tools=%d finish=%s usage=%s",
            self._litellm_model,
            elapsed,
            chunk_count,
            content_chars,
            reasoning_chars,
            len(accumulated_tool_calls),
            finish,
            stream_usage,
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

    def count_tokens(self, messages: list[dict]) -> int:
        return self._token_counter.count_messages(messages, self.model)
