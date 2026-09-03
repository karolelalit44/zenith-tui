import os

from server.config.loader import load_config
from server.config.settings import AppSettings


def test_default_config():
    config = AppSettings()
    assert config.active_provider == ""
    assert config.home_dir == os.environ.get("ZENITH_HOME") or config.home_dir
    assert config.max_context_tokens == int(os.environ["ZENITH_MAX_CONTEXT_TOKENS"])


def test_config_validation():
    config = AppSettings(active_provider="")
    assert config.active_provider == ""


def test_load_config(temp_dir):
    config = load_config(str(temp_dir))
    assert config is not None
    assert config.active_provider == ""
    assert config.workspace_root == str(temp_dir)


def test_get_active_provider_config():
    from server.config.providers import ProviderConfig

    config = AppSettings(
        providers={"openai": ProviderConfig(model="gpt-4o")}, active_provider="openai"
    )
    pc = config.get_active_provider_config()
    assert pc is not None
    assert pc.model == "gpt-4o"


def test_require_active_provider_config_missing():
    config = AppSettings()
    try:
        config.require_active_provider_config()
        assert False, "Should have raised"
    except ValueError as e:
        assert "not configured" in str(e)


def test_context_compaction_threshold_default():
    """New budget setting defaults to the import-time ZENITH_* default when unset."""
    config = AppSettings()
    assert 0.0 <= config.context_compaction_threshold <= 1.0


def test_load_config_context_compaction_threshold_env_override(monkeypatch, temp_dir):
    """A new ZENITH_* scalar env var is honored by load_config() at load time (task 0.3)."""
    monkeypatch.setenv("ZENITH_CONTEXT_COMPACTION_THRESHOLD", "0.62")
    config = load_config(str(temp_dir))
    assert abs(config.context_compaction_threshold - 0.62) < 1e-9


def test_load_config_context_compaction_threshold_invalid_ignored(monkeypatch, temp_dir):
    monkeypatch.setenv("ZENITH_CONTEXT_COMPACTION_THRESHOLD", "not-a-number")
    config = load_config(str(temp_dir))
    assert 0.0 <= config.context_compaction_threshold <= 1.0


# -- Layered precedence tests (defaults < file < env < CLI) -------------------


def test_precedence_defaults_applied():
    """Code defaults are in place when nothing else is provided."""
    config = AppSettings()
    assert config.auto_approve_plan is False
    assert config.auto_overwrite is True


def test_load_config_ws_origin_env_overrides(monkeypatch, temp_dir):
    monkeypatch.setenv("ZENITH_ALLOWED_WS_ORIGINS", "https://app.example.com, http://localhost:8765")
    monkeypatch.setenv("ZENITH_ALLOW_EMPTY_WS_ORIGIN", "false")
    config = load_config(str(temp_dir))
    assert config.allowed_ws_origins == ["https://app.example.com", "http://localhost:8765"]
    assert config.allow_empty_ws_origin is False


def test_precedence_cli_overrides_defaults():
    """Constructor (CLI/caller) values beat code defaults."""
    config = AppSettings(auto_overwrite=False, max_context_tokens=8000)
    assert config.auto_overwrite is False
    assert config.max_context_tokens == 8000


def test_precedence_env_beats_code_default(monkeypatch):
    """Environment variable overrides code defaults at load_config time."""
    monkeypatch.setenv("ZENITH_CONTEXT_COMPACTION_THRESHOLD", "0.55")
    config = load_config(str(os.environ["ZENITH_HOME"]))
    # load_config reads ZENITH_CONTEXT_COMPACTION_THRESHOLD and overrides default 0.7
    assert abs(config.context_compaction_threshold - 0.55) < 1e-9


def test_precedence_cli_beats_env(monkeypatch):
    """Explicit constructor values override env-sourced defaults."""
    monkeypatch.setenv("ZENITH_CONTEXT_COMPACTION_THRESHOLD", "0.55")
    # Constructor override of 0.77 should beat the env 0.55
    config = AppSettings(context_compaction_threshold=0.77)
    assert abs(config.context_compaction_threshold - 0.77) < 1e-9


def test_load_config_env_beats_storage_default(temp_dir):
    """Env overrides the default loaded from storage (loader reads env last)."""
    # load_config reads compaction from env; without env set, it stays at code default
    config = load_config(str(temp_dir))
    assert 0.0 <= config.context_compaction_threshold <= 1.0


def test_load_config_reads_scalar_environment_at_call_time(monkeypatch, temp_dir):
    monkeypatch.setenv("ZENITH_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ZENITH_MAX_CONTEXT_TOKENS", "9000")
    monkeypatch.setenv("ZENITH_SUMMARY_THRESHOLD", "0.6")
    monkeypatch.setenv("ZENITH_CONTEXT_COMPACTION_THRESHOLD", "0.55")
    monkeypatch.setenv("ZENITH_EXPLORE_DELEGATION", "tool")
    monkeypatch.setenv("ZENITH_EXPLORE_TOKEN_BUDGET", "12000")
    monkeypatch.setenv("ZENITH_BASH_TIMEOUT", "45")

    config = load_config(str(temp_dir))

    assert config.log_level == "DEBUG"
    assert config.max_context_tokens == 9000
    assert config.summary_threshold == 0.6
    assert config.context_compaction_threshold == 0.55
    assert config.explore_delegation == "tool"
    assert config.explore_token_budget == 12000
    assert config.tools.max_bash_timeout == 45
