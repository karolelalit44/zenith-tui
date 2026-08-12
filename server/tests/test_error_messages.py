"""Regression tests for clean provider-error extraction (todo/03).

Covers:
- `_unwrap_bytes_literal` strips the ``b'...'`` wrapper litellm embeds around
  Google's JSON error body and decodes the repr's `\n` escapes.
- `_extract_json_error_message` prefers the nested ``error.message``.
- `_extract_clean_message` returns the clean inner message for bytes-wrapped
  JSON instead of the raw blob.
- A 429 with a ``b'{...}'`` body classifies as `recoverable=True` and carries a
  clean message, provider, and parsed retry delay.
- `responder.error` emits `provider`/`action`/`hint` only when set.
"""

import pytest

from server.domain.errors import RateLimitError
from server.providers import responder
from server.providers.llm_provider import (
    _classify_provider_error,
    _extract_clean_message,
    _extract_json_error_message,
    _unwrap_bytes_literal,
)


def _bytes_wrapped_429() -> str:
    # str(exc) as surfaced by litellm: the body is the repr of a bytes object,
    # so newlines appear as literal backslash-n characters inside the wrapper.
    return (
        "litellm.RateLimitError: vertex_ai_betaException - b'{\\n"
        '  "error": {\\n'
        '    "code": 429,\\n'
        '    "message": "429 Quota exceeded for metric '
        "generativelanguage.googleapis.com/generate_content_free_tier_requests, "
        'limit: 15",\\n'
        '    "status": "RESOURCE_EXHAUSTED",\\n'
        '    "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", '
        '"retryDelay": "9.788501089s"}]\\n'
        "  },\\n"
        '  "retryDelay": "9.788501089s"\\n'
        "}'"
    )


# ---------------------------------------------------------------------------
# _unwrap_bytes_literal
# ---------------------------------------------------------------------------


def test_unwrap_bytes_literal_strips_wrapper_and_unescapes():
    unwrapped = _unwrap_bytes_literal(_bytes_wrapped_429())
    assert not unwrapped.startswith("b'")
    assert "\\n" not in unwrapped
    assert '"message": "429 Quota exceeded' in unwrapped
    assert '"retryDelay": "9.788501089s"' in unwrapped


def test_unwrap_bytes_literal_double_quote_marker():
    text = 'b"{\\"error\\": {\\"message\\": \\"boom\\"}}"'
    assert _unwrap_bytes_literal(text) == '{"error": {"message": "boom"}}'


def test_unwrap_bytes_literal_noop_without_wrapper():
    text = '{"error": {"message": "boom"}}'
    assert _unwrap_bytes_literal(text) == text


# ---------------------------------------------------------------------------
# _extract_json_error_message
# ---------------------------------------------------------------------------


def test_extract_json_error_message_prefers_nested_error():
    text = 'prefix garbage {"error": {"message": "the clean one", "status": "X"}, "message": "top level"}'
    assert _extract_json_error_message(text) == "the clean one"


def test_extract_json_error_message_falls_back_to_top_level():
    text = 'prefix {"message": "top level only"}'
    assert _extract_json_error_message(text) == "top level only"


def test_extract_json_error_message_empty_when_no_json():
    assert _extract_json_error_message("no json here") == ""
    assert _extract_json_error_message("") == ""


# ---------------------------------------------------------------------------
# _extract_clean_message
# ---------------------------------------------------------------------------


def test_extract_clean_message_bytes_wrapped_429():
    """The observed Google 429 case: bytes-wrapped JSON must become clean text."""
    clean = _extract_clean_message(RuntimeError(_bytes_wrapped_429()))
    assert clean == (
        "429 Quota exceeded for metric "
        "generativelanguage.googleapis.com/generate_content_free_tier_requests, "
        "limit: 15"
    )
    assert "b'" not in clean
    assert "litellm.RateLimitError" not in clean
    assert "vertex_ai_betaException" not in clean


def test_extract_clean_message_plain_json_body():
    clean = _extract_clean_message(
        RuntimeError(
            'litellm.APIError: vertex_ai_betaException - {"error": {"message": "bad request"}}'
        )
    )
    assert clean == "bad request"


def test_extract_clean_message_litellm_provider_prefix_fallback():
    raw = "litellm.AuthenticationError: OpenAIException - 401 Unauthorized"
    clean = _extract_clean_message(RuntimeError(raw))
    assert "litellm.AuthenticationError" not in clean
    assert "OpenAIException" not in clean


def test_extract_clean_message_non_json_fallback():
    raw = "some generic failure"
    assert _extract_clean_message(RuntimeError(raw)) == raw


# ---------------------------------------------------------------------------
# Classification + event emission regression (todo/03 happy path)
# ---------------------------------------------------------------------------


def test_classified_429_with_bytes_body_is_clean_and_recoverable():
    exc = _classify_provider_error(RuntimeError(_bytes_wrapped_429()), "google")
    assert isinstance(exc, RateLimitError)
    assert exc.recoverable is True
    assert exc.provider == "google"
    assert exc.retry_after == pytest.approx(9.788501089)
    message = str(exc)
    assert "Quota exceeded for metric" in message
    assert "b'" not in message
    assert "litellm.RateLimitError" not in message


def test_error_event_carries_provider_action_hint():
    event = responder.error(
        "clean message",
        session_id="s1",
        code="RATE_LIMIT",
        recoverable=True,
        provider="google",
        action="retry",
        hint="Wait for the rate limit to reset, then retry this prompt.",
    )
    assert event.data["message"] == "clean message"
    assert event.data["provider"] == "google"
    assert event.data["action"] == "retry"
    assert event.data["hint"].startswith("Wait for the rate limit")
    assert event.data["recoverable"] is True


def test_error_event_omits_empty_optional_fields():
    event = responder.error("oops", session_id="s1", code="BAD_REQUEST")
    assert event.data["code"] == "BAD_REQUEST"
    assert "provider" not in event.data
    assert "action" not in event.data
    assert "hint" not in event.data
