from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from server.domain.domain import ScenarioMode, SessionState
from server.domain.events import Event, EventKind
from server.domain.message import Message
from server.domain.session import Session
from server.sessions.export import SessionExporter
from server.sessions.import_service import SessionImporter
from server.storage import StorageHome, ensure_materialized
from server.storage.session_file import locate
from server.storage.session_store import FileMessageRepository, FileSessionRepository


@pytest.fixture()
def home(temp_dir: Path) -> StorageHome:
    h = StorageHome(temp_dir)
    ensure_materialized(h)
    return h


class TestFileStorageLayout:
    async def test_materialization_creates_catalog(self, home: StorageHome):
        assert home.catalog_path.exists()
        assert not (home.root / "providers.json").exists()
        assert not (home.root / "models.json").exists()
        text = home.catalog_path.read_text(encoding="utf-8")
        for pid in ("gemini", "groq", "openrouter", "openai_compatible"):
            assert f'"id": "{pid}"' in text
        # First-class roster is exact (decision D3): no legacy vendors.
        for gone in ('openai"', '"nvidia"', '"tokenrouter"', '"anthropic"'):
            assert f'"id": {gone}' not in text.replace('"id": "openai_compatible"', "")

    async def test_secret_never_in_catalog_files(self, home: StorageHome):
        from server.storage.provider_config import save_provider_config

        save_provider_config(
            home,
            provider="groq",
            api_key="gsk_super_secret_value",
            model="llama-3.3-70b-versatile",
            base_url="",
            max_tokens=4096,
            temperature=0.7,
        )
        for name in ("zenith_catalog.json",):
            body = (home.root / name).read_text(encoding="utf-8")
            assert "gsk_super_secret_value" not in body
        profile = (home.root / "user_profile.json").read_text(encoding="utf-8")
        assert "gsk_super_secret_value" in profile


class TestCatalogMigration:
    def test_stale_legacy_files_purged_even_when_catalog_already_exists(self, temp_dir: Path):
        import json

        home = StorageHome(temp_dir)
        home.root.mkdir(parents=True, exist_ok=True)
        ensure_materialized(home)
        assert home.catalog_path.exists()
        # Simulate a partial prior migration: a stale two-file layout was left
        # behind even though the single catalog already exists.
        (home.root / "providers.json").write_text(
            json.dumps({"version": 1, "providers": []}), encoding="utf-8"
        )
        (home.root / "models.json").write_text(
            json.dumps({"version": 1, "models": {}}), encoding="utf-8"
        )
        ensure_materialized(home)
        assert not (home.root / "providers.json").exists()
        assert not (home.root / "models.json").exists()
        assert home.catalog_path.exists()

    def test_legacy_two_files_migrate_to_single_catalog(self, temp_dir: Path):
        import json

        home = StorageHome(temp_dir)
        home.root.mkdir(parents=True, exist_ok=True)
        (home.root / "providers.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "seedVersion": 0,
                    "providers": [
                        {
                            "id": "groq",
                            "name": "Groq",
                            "adapter": "groq",
                            "source": "builtin",
                            "sortOrder": 1,
                        },
                        {"id": "myprov", "name": "My Provider", "source": "user"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (home.root / "models.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "seedVersion": 0,
                    "models": {
                        "groq/abc": {
                            "providerId": "groq",
                            "id": "abc",
                            "name": "ABC",
                            "contextWindow": 128000,
                            "source": "user",
                        },
                        "myprov/x": {
                            "providerId": "myprov",
                            "id": "x",
                            "name": "X",
                            "source": "user",
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        ensure_materialized(home)

        assert home.catalog_path.exists()
        assert not (home.root / "providers.json").exists()
        assert not (home.root / "models.json").exists()

        doc = json.loads(home.catalog_path.read_text(encoding="utf-8"))
        providers = {p["id"]: p for p in doc["providers"]}
        assert set(providers) >= {"groq", "myprov"}, "migration lost providers"
        groq_ids = {m["id"] for m in providers["groq"]["models"]}
        assert "abc" in groq_ids, "legacy groq model lost in migration"
        myprov_ids = {m["id"] for m in providers["myprov"]["models"]}
        assert "x" in myprov_ids, "legacy user provider model lost in migration"

    def test_fresh_materialization_matches_builtin_seed_shape(self, temp_dir: Path):
        import json

        from server.storage import builtin_seed

        home = StorageHome(temp_dir)
        ensure_materialized(home)
        doc = json.loads(home.catalog_path.read_text(encoding="utf-8"))
        assert doc["version"] == 2
        assert doc["seedVersion"] == builtin_seed.SEED_VERSION
        by_id = {p["id"]: p for p in doc["providers"]}
        for seed in builtin_seed.PROVIDERS:
            disk = by_id[seed["id"]]
            assert isinstance(disk["models"], list), "provider must carry a nested models list"
            assert len(disk["models"]) == len(seed["models"]), (
                f"provider {seed['id']} model count drifted from seed"
            )


class TestSessionJsonlExportImportRoundtrip:
    """The JSONL export format doubles as the on-disk history shape."""

    @pytest.mark.asyncio
    async def test_export_and_import_roundtrip(self, temp_dir: Path):
        source_home = StorageHome(temp_dir / "src")
        ensure_materialized(source_home)
        session_repo = FileSessionRepository(source_home)
        message_repo = FileMessageRepository(source_home)

        session = Session(
            id="sess-roundtrip-123",
            title="Design Storage Plan",
            mode=ScenarioMode.PLAN,
            state=SessionState.CREATED,
            created_at=datetime(2026, 8, 15, 12, 0, 0),
            updated_at=datetime(2026, 8, 15, 12, 5, 0),
            model="gemini-3.5-flash-lite",
            provider="gemini",
            total_tokens=1500,
            metadata={"custom_tag": "persistence_test"},
        )
        await session_repo.create(session)

        msg1 = Message(
            id="msg-1",
            session_id=session.id,
            role="user",
            content="How should we design persistence?",
            token_count=10,
            created_at=datetime(2026, 8, 15, 12, 0, 1),
        )
        msg2 = Message(
            id="msg-2",
            session_id=session.id,
            role="assistant",
            content="Use files for operational storage and JSONL for export.",
            events=[
                Event(
                    kind=EventKind.TOOL_CALL,
                    data={"tool": "file_read", "params": {"path": "config.py"}},
                    session_id=session.id,
                ),
                Event(
                    kind=EventKind.MESSAGE,
                    data={"text": "Use files for operational storage and JSONL for export."},
                    session_id=session.id,
                ),
            ],
            token_count=25,
            created_at=datetime(2026, 8, 15, 12, 0, 5),
        )
        await message_repo.append(msg1)
        await message_repo.append(msg2)

        exporter = SessionExporter()
        export_path = exporter.export_jsonl(
            session, [msg1, msg2], output_dir=str(temp_dir / "exports")
        )
        assert Path(export_path).exists()

        target_home = StorageHome(temp_dir / "dst")
        ensure_materialized(target_home)
        clean_srepo = FileSessionRepository(target_home)
        clean_mrepo = FileMessageRepository(target_home)
        importer = SessionImporter(clean_srepo, clean_mrepo)

        imported_sess, imported_msgs = await importer.import_from_jsonl(export_path)

        assert imported_sess.id == session.id
        assert imported_sess.title == "Design Storage Plan"
        assert imported_sess.mode == ScenarioMode.PLAN
        assert imported_sess.provider == "gemini"
        assert imported_sess.model == "gemini-3.5-flash-lite"
        assert imported_sess.metadata == {"custom_tag": "persistence_test"}

        assert len(imported_msgs) == 2
        assert imported_msgs[0].role == "user"
        assert imported_msgs[0].content == "How should we design persistence?"
        assert imported_msgs[1].role == "assistant"
        assert imported_msgs[1].content == "Use files for operational storage and JSONL for export."
        assert len(imported_msgs[1].events) == 2
        assert imported_msgs[1].events[0].kind == EventKind.TOOL_CALL

    @pytest.mark.asyncio
    async def test_corrupt_trailing_line_is_tolerated(self, temp_dir: Path):
        home = StorageHome(temp_dir)
        ensure_materialized(home)
        srepo = FileSessionRepository(home)
        mrepo = FileMessageRepository(home)
        session = await srepo.create(Session(id="sess-corrupt", title="t"))
        await mrepo.append(
            Message(session_id=session.id, role="user", content="hello", token_count=2)
        )
        events_path = locate(home, session.id)
        assert events_path is not None
        with open(events_path, "a", encoding="utf-8") as f:
            f.write('{"t": "msg", "id": "partial")\n')  # corrupt trailing line
        history = await mrepo.get_by_session(session.id)
        assert len(history) == 1
        assert history[0].content == "hello"
