import os
import tempfile
from pathlib import Path

import server.config.environment  # noqa: F401

# Storage stays isolated to a fresh temp home per test run, never ~/.zenith.
_test_tmpdir = tempfile.mkdtemp()
os.environ["ZENITH_HOME"] = _test_tmpdir

import pytest

from server.config.settings import AppSettings
from server.domain.events import Event, EventKind
from server.storage import (
    FileCheckpointRepository,
    FileMessageRepository,
    FileSessionRepository,
    FileSyncEventRepository,
    FileTokenUsageRepository,
    StorageHome,
    ensure_materialized,
)


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def home(temp_dir):
    """Isolated file-storage home rooted in a per-test temp dir."""
    h = StorageHome(temp_dir)
    ensure_materialized(h)
    return h


@pytest.fixture
def config(temp_dir):
    return AppSettings(home_dir=str(temp_dir), workspace_root=str(temp_dir))


@pytest.fixture
def session_repo(home):
    return FileSessionRepository(home)


@pytest.fixture
def message_repo(home):
    return FileMessageRepository(home)


@pytest.fixture
def sync_repo(home):
    return FileSyncEventRepository(home)


@pytest.fixture
def checkpoint_repo(home):
    return FileCheckpointRepository(home)


@pytest.fixture
def usage_repo(home):
    return FileTokenUsageRepository(home)


@pytest.fixture
def sample_event():
    return Event(kind=EventKind.MESSAGE, data={"text": "Hello, World!"})
