import pytest

from server.config import environment
from server.config.environment import (
    ZENITH_ASYNC_SUMMARY_ENABLED,
    ZENITH_HOST,
    ZENITH_PORT,
    ZENITH_TEMPERATURE,
    get_bool,
    get_env,
    get_float,
    get_int,
)


def test_environment_explicit_values_defined():
    """All required environment keys are defined as direct constants."""
    expected_keys = [
        "ZENITH_HOST",
        "ZENITH_PORT",
        "ZENITH_HOME",
        "ZENITH_LOG_LEVEL",
        "ZENITH_MAX_CONTEXT_TOKENS",
        "ZENITH_SUMMARY_THRESHOLD",
        "ZENITH_CONTEXT_COMPACTION_THRESHOLD",
        "ZENITH_ASYNC_SUMMARY_ENABLED",
        "ZENITH_MAX_TOOL_OUTPUT",
        "ZENITH_BASH_TIMEOUT",
        "ZENITH_GIT_TIMEOUT",
        "ZENITH_WEBFETCH_TIMEOUT",
        "ZENITH_WEBFETCH_MAX_BYTES",
        "ZENITH_WEBSEARCH_TIMEOUT",
        "ZENITH_VALIDATION_TIMEOUT",
        "ZENITH_SUMMARIZER_TIMEOUT",
        "ZENITH_MAX_TOKENS",
        "ZENITH_TEMPERATURE",
        "ZENITH_WS_MAX_RECONNECT",
        "ZENITH_WS_RECONNECT_DELAY",
        "ZENITH_WS_RPC_TIMEOUT",
        "ZENITH_GIT_CACHE_TTL",
        "ZENITH_EXPLORE_DELEGATION",
        "ZENITH_EXPLORE_TOKEN_BUDGET",
        "ZENITH_ENRICH_TIMEOUT",
        "ZENITH_SALVAGE_TIMEOUT",
        "ZENITH_MIN_REQUEST_INTERVAL",
    ]
    for key in expected_keys:
        assert hasattr(environment, key), f"Constant '{key}' missing from environment module"


def test_get_env_picks_explicit_config():
    """get_env directly picks the defined configuration value."""
    val = get_env("ZENITH_HOST")
    assert val == str(ZENITH_HOST)


def test_get_int_picks_explicit_config():
    """get_int parses integer directly from configuration."""
    port = get_int("ZENITH_PORT")
    assert port == ZENITH_PORT


def test_get_float_picks_explicit_config():
    """get_float parses float directly from configuration."""
    temp = get_float("ZENITH_TEMPERATURE")
    assert temp == ZENITH_TEMPERATURE


def test_get_bool_picks_explicit_config():
    """get_bool parses bool directly from configuration."""
    async_summary = get_bool("ZENITH_ASYNC_SUMMARY_ENABLED")
    assert async_summary == ZENITH_ASYNC_SUMMARY_ENABLED


def test_missing_key_raises_key_error():
    """Requesting an undefined key raises KeyError with no fallback allowed."""
    with pytest.raises(KeyError, match="not defined in environment configuration"):
        get_env("NONEXISTENT_ZENITH_CONFIG_KEY")


def test_process_env_override(monkeypatch):
    """Setting process environment variable overrides the defined default."""
    monkeypatch.setenv("ZENITH_PORT", "9999")
    assert get_int("ZENITH_PORT") == 9999


def test_invalid_type_conversions(monkeypatch):
    """Invalid conversions raise ValueError rather than falling back."""
    monkeypatch.setenv("ZENITH_PORT", "not-a-number")
    with pytest.raises(ValueError, match="cannot be parsed as int"):
        get_int("ZENITH_PORT")

    monkeypatch.setenv("ZENITH_TEMPERATURE", "invalid-float")
    with pytest.raises(ValueError, match="cannot be parsed as float"):
        get_float("ZENITH_TEMPERATURE")

    monkeypatch.setenv("ZENITH_ASYNC_SUMMARY_ENABLED", "maybe")
    with pytest.raises(ValueError, match="cannot be parsed as bool"):
        get_bool("ZENITH_ASYNC_SUMMARY_ENABLED")
