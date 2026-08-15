import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

# .env is the single source of truth for config; explicitly set env vars win.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

# DB stays isolated to a fresh temp file per test run, never the real zenith.db.
_test_tmpdir = tempfile.mkdtemp()
os.environ["ZENITH_DB_PATH"] = os.path.join(_test_tmpdir, "test.db")

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
