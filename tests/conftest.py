import pytest
import tempfile
from pathlib import Path

from zenith.config.settings import AppSettings
from zenith.db.connection import Database
from zenith.core.events import Event, EventKind


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
