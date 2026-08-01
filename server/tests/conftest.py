"""Test configuration — sets required env vars before any zenith imports."""

import os
import tempfile

# ── Set ALL required env vars BEFORE importing anything from ──
_test_tmpdir = tempfile.mkdtemp()

_env_defaults = {
    "ZENITH_ACTIVE_PROVIDER": "nvidia",
    "ZENITH_DB_PATH": os.path.join(_test_tmpdir, "test.db"),
    "ZENITH_LOG_LEVEL": "info",
    "ZENITH_MAX_CONTEXT_TOKENS": "128000",
    "ZENITH_SUMMARY_THRESHOLD": "0.8",
    "ZENITH_BASH_TIMEOUT": "30",
    "ZENITH_MAX_ITERATIONS": "25",
    "ZENITH_MAX_TOOL_OUTPUT": "10000",
    "ZENITH_MAX_RETRIES": "3",
    "ZENITH_STREAM_MAX_RETRIES": "2",
    "ZENITH_RETRY_BASE_DELAY": "1.0",
    "ZENITH_RETRY_MAX_DELAY": "60.0",
    "ZENITH_VALIDATION_TIMEOUT": "30",
    "ZENITH_WEBFETCH_TIMEOUT": "30",
    "ZENITH_WEBFETCH_MAX_BYTES": "50000",
    "ZENITH_GIT_TIMEOUT": "30",
    "ZENITH_MAX_TOKENS": "4096",
    "ZENITH_TEMPERATURE": "0.7",
    # Frontend env vars (used by TS tests)
    "ZENITH_WS_MAX_RECONNECT": "5",
    "ZENITH_WS_RECONNECT_DELAY": "1000",
    "ZENITH_WS_RPC_TIMEOUT": "60000",
    "ZENITH_GIT_CACHE_TTL": "30000",
    "VITE_BACKEND_URL": "http://localhost:8765",
    "VITE_BACKEND_FETCH_TIMEOUT": "5000",
    "VITE_DEFAULT_MAX_TOKENS": "4096",
    "VITE_DEFAULT_TEMPERATURE": "0.7",
    "VITE_FALLBACK_MAX_TOKENS": "30000",
}

for key, val in _env_defaults.items():
    os.environ.setdefault(key, val)

# ── Now safe to import zenith modules ──

from pathlib import Path

import pytest

from server.config.settings import AppSettings
from server.domain.events import Event, EventKind
from server.persistence.connection import Database


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def config(temp_dir):
    return AppSettings(db_path=str(temp_dir / "test.db"), workspace_root=str(temp_dir))


@pytest.fixture
async def db(config):
    database = Database(config.db_path)
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
def sample_event():
    return Event(kind=EventKind.MESSAGE, data={"text": "Hello, World!"})
