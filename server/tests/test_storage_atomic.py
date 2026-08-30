"""File-storage robustness: atomic writes, crash tolerance, concurrency."""

from __future__ import annotations

import asyncio
import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from server.domain.message import Message
from server.domain.session import Session
from server.storage import (
    StorageHome,
    ensure_materialized,
    read_json,
    write_json_atomic,
)
from server.storage import session_store as session_store_mod
from server.storage.atomic import read_jsonl, rewrite_jsonl_atomic
from server.storage.catalog_compat import invalidate_catalog_cache, load_catalog
from server.storage.catalog_store import upsert_model, upsert_provider
from server.storage.profile_store import load_profile, save_profile, set_api_key
from server.storage.session_store import (
    FileMessageRepository,
    FileSessionRepository,
)


class TestAtomicWrites:
    def test_write_and_read_roundtrip(self, temp_dir: Path):
        path = temp_dir / "nested" / "doc.json"
        write_json_atomic(path, {"a": 1, "b": [1, 2]})
        assert read_json(path) == {"a": 1, "b": [1, 2]}

    def test_no_tmp_leftovers(self, temp_dir: Path):
        path = temp_dir / "x.json"
        for i in range(5):
            write_json_atomic(path, {"i": i})
        leftovers = list(temp_dir.glob(".*tmp*"))
        assert leftovers == []

    def test_unique_tmp_names_under_parallel_writers(self, temp_dir: Path):
        # Regression (review #1): tmp names embed pid+uuid so two writers
        # can never target the same temp file.
        path = temp_dir / "doc.json"

        def write(i: int) -> None:
            write_json_atomic(path, {"i": i})

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(write, range(32)))
        assert read_json(path)["i"] in range(32)
        assert list(temp_dir.glob(".*tmp*")) == []

    def test_bak_holds_previous_known_good(self, temp_dir: Path):
        # Regression (review #4): .bak is written BEFORE the primary is
        # replaced, so it always holds the last known-good payload.
        path = temp_dir / "doc.json"
        write_json_atomic(path, {"version": 1})
        write_json_atomic(path, {"version": 2})
        assert read_json(path) == {"version": 2}
        assert read_json(path.with_suffix(path.suffix + ".bak")) == {"version": 1}

    def test_corrupt_primary_falls_back_to_previous_good(self, temp_dir: Path):
        path = temp_dir / "doc.json"
        write_json_atomic(path, {"version": 1})
        write_json_atomic(path, {"version": 2})
        path.write_text("{corrupt", encoding="utf-8")
        # v2 never reached disk as good data, so the previous known-good
        # (v1) is restored — not a fabricated newer version.
        assert read_json(path) == {"version": 1}

    def test_missing_returns_default(self, temp_dir: Path):
        assert read_json(temp_dir / "nope.json", None) is None

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
    def test_private_files_get_0600(self, temp_dir: Path):
        # Regression (review #10): secret-bearing files are owner-only.
        home = StorageHome(temp_dir)
        ensure_materialized(home)
        profile = load_profile(home)
        set_api_key(profile, "gemini", "AQ.secret123")
        save_profile(home, profile)
        mode = stat.S_IMODE(os.stat(home.profile_path).st_mode)
        assert mode == 0o600


class TestJsonlRobustness:
    def test_rewrite_replaces_content(self, temp_dir: Path):
        path = temp_dir / "log.jsonl"
        path.write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
        n = rewrite_jsonl_atomic(path, [{"b": 1}, {"b": 2}, {"b": 3}])
        assert n == 3
        assert [r["b"] for r in read_jsonl(path)] == [1, 2, 3]

    def test_partial_trailing_line_skipped(self, temp_dir: Path):
        path = temp_dir / "log.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"ok": true}\n')
            f.flush()
            f.write('{"trunc')  # simulates a crash mid-append
        records = read_jsonl(path)
        assert records == [{"ok": True}]

    def test_read_error_propagates_not_silently_empty(self, temp_dir, monkeypatch):
        # Regression (review #2): an OSError during read must surface —
        # mapping it to [] turned transient IO failures into data loss.
        path = temp_dir / "log.jsonl"
        path.write_text('{"a": 1}\n', encoding="utf-8")

        real_open = open

        def failing_open(file, *args, **kwargs):
            if Path(str(file)) == path:
                raise OSError("simulated transient IO failure")
            return real_open(file, *args, **kwargs)

        monkeypatch.setattr("builtins.open", failing_open)
        with pytest.raises(OSError):
            read_jsonl(path)


class TestHistoryDestructionGuards:
    """Regression (review #2): no rewrite may be based on a failed/empty read."""

    async def _seed(self, temp_dir: Path, n: int = 3):
        home = StorageHome(temp_dir)
        ensure_materialized(home)
        srepo = FileSessionRepository(home)
        mrepo = FileMessageRepository(home)
        s = await srepo.create(Session(id="sess-iofail", title="t", workspace_root=str(temp_dir)))
        for i in range(n):
            await mrepo.append(
                Message(session_id=s.id, role="user", content=f"m{i}", token_count=i)
            )
        return home, srepo, mrepo, s

    def _record_count(self, home, sid: str) -> int:
        from server.storage.session_file import iter_records

        return len(iter_records(home, sid))

    async def test_compaction_aborts_on_read_error(self, temp_dir, monkeypatch):
        home, _srepo, mrepo, s = await self._seed(temp_dir)
        before = self._record_count(home, s.id)

        def boom(path):
            raise OSError("simulated transient IO failure")

        monkeypatch.setattr(session_store_mod, "read_jsonl", boom)
        with pytest.raises(OSError):
            await mrepo.compact_history(s.id, metadata={"summary": "x"}, delete_ids=[])
        # History untouched — the failure surfaced before any rewrite.
        assert self._record_count(home, s.id) == before

    async def test_empty_messages_with_nonzero_stats_aborts_compaction(self, temp_dir):
        # Craft the anomaly directly: header + stats claim messages exist,
        # but the file carries no msg records (e.g. lost to external damage).
        home, _srepo, mrepo, s = await self._seed(temp_dir, n=0)
        path = session_store_mod.locate(home, s.id)
        assert path is not None
        lines = read_jsonl(path)
        stats = next(r for r in lines if r.get("t") == "stats")
        stats["message_count"] = 3
        stats["user_message_count"] = 3
        rewrite_jsonl_atomic(path, [r for r in lines if r.get("t") != "stats"] + [stats])

        deleted = await mrepo.compact_history(s.id, metadata={"summary": "x"}, delete_ids=[])
        assert deleted == 0, "empty message set must abort compaction, not truncate"
        assert len(read_jsonl(path)) == len(lines)

    async def test_sync_delete_propagates_read_error(self, temp_dir, monkeypatch):
        from server.storage.session_store import FileSyncEventRepository

        home, _srepo, _mrepo, s = await self._seed(temp_dir, n=1)
        sync_repo = FileSyncEventRepository(home)
        before = self._record_count(home, s.id)

        def boom(path):
            raise OSError("simulated transient IO failure")

        monkeypatch.setattr(session_store_mod, "read_jsonl", boom)
        with pytest.raises(OSError):
            await sync_repo.delete_by_session(s.id)
        assert self._record_count(home, s.id) == before

    async def test_sync_delete_never_touches_missing_session(self, temp_dir):
        from server.storage.session_store import FileSyncEventRepository

        home, _srepo, _mrepo, s = await self._seed(temp_dir, n=0)
        sync_repo = FileSyncEventRepository(home)
        path = session_store_mod.locate(home, s.id)
        assert path is not None
        await sync_repo.delete_by_session(s.id)
        # No sync records existed; the file must be unchanged (not blanked).
        assert path.exists()

    async def test_sync_delete_preserves_message_lines(self, temp_dir):
        from server.storage.session_store import FileSyncEventRepository

        home, _srepo, _mrepo, s = await self._seed(temp_dir, n=1)
        sync_repo = FileSyncEventRepository(home)
        await sync_repo.record(s.id, "state_change", {"state": "running"})
        await sync_repo.delete_by_session(s.id)
        remaining = read_jsonl(session_store_mod.locate(home, s.id))
        assert remaining
        assert all(r.get("t") != "sync" for r in remaining)
        assert any(r.get("t") == "msg" for r in remaining)


class TestConcurrentTokenAppends:
    async def test_parallel_add_tokens_lose_no_increments(self, temp_dir: Path):
        home = StorageHome(temp_dir)
        ensure_materialized(home)
        srepo = FileSessionRepository(home)
        s = await srepo.create(Session(id="sess-tokens", title="t", workspace_root=str(temp_dir)))

        increments = [(1, 0.01)] * 50 + [(5, 0.0)] * 25 + [(0, 0.1)] * 25
        await asyncio.gather(*(srepo.add_tokens(s.id, tok, cost) for tok, cost in increments))

        got = await srepo.get(s.id)
        assert got is not None
        expected_tokens = sum(t for t, _ in increments)
        expected_cost = sum(c for _, c in increments)
        assert got.total_tokens == expected_tokens
        assert abs(got.total_cost - expected_cost) < 1e-9


class TestCatalogCacheVisibility:
    def test_cached_catalog_sees_writes_without_restart(self, temp_dir: Path):
        # Regression (review #3): catalog caches were only invalidated by
        # tests, so user edits stayed invisible until process restart.
        invalidate_catalog_cache()
        home = StorageHome(temp_dir)
        ensure_materialized(home)
        load_catalog(home)  # prime the cache

        upsert_provider(
            home,
            {
                "id": "cache_prov",
                "name": "Cache Prov",
                "adapter": "openai_compatible",
                "baseUrl": "http://localhost:9999/v1",
            },
        )
        upsert_model(
            home,
            {
                "providerId": "cache_prov",
                "id": "cache-model",
                "name": "Cache Model",
                "contextWindow": 4096,
            },
        )
        catalog = load_catalog(home)  # same process, no manual invalidation
        assert "cache_prov" in catalog.get("providers", {})
        models = {m["id"] for m in catalog["providers"]["cache_prov"].get("models", [])}
        assert "cache-model" in models

    async def test_price_cache_refreshes_on_catalog_change(self, temp_dir: Path):
        from server.storage.usage_store import FileTokenUsageRepository

        invalidate_catalog_cache()
        home = StorageHome(temp_dir)
        ensure_materialized(home)
        repo = FileTokenUsageRepository(home)

        unknown = repo._resolve_price("groq", "brand-new-model")
        assert unknown == {"input": 0.0, "output": 0.0, "cache_read": 0.0, "cache_creation": 0.0}

        upsert_model(
            home,
            {
                "providerId": "groq",
                "id": "brand-new-model",
                "name": "New",
                "contextWindow": 1024,
                "pricing": {"input": 3.0, "output": 15.0},
            },
        )
        priced = repo._resolve_price("groq", "brand-new-model")
        assert priced == {"input": 3.0, "output": 15.0, "cache_read": 0.0, "cache_creation": 0.0}


class TestSeedRefreshPreservesEdits:
    def _age_seed(self, home: StorageHome, doc_path: Path) -> None:
        from server.storage import catalog_store

        doc = read_json(doc_path, {})
        doc["seedVersion"] = catalog_store.builtin_seed.SEED_VERSION - 1
        write_json_atomic(doc_path, doc)

    def test_edited_builtin_provider_survives_seed_bump(self, temp_dir: Path):
        home = StorageHome(temp_dir)
        ensure_materialized(home)
        upsert_provider(
            home,
            {
                "id": "groq",
                "name": "Groq via my proxy",
                "baseUrl": "http://my-proxy.local/v1",
            },
        )
        self._age_seed(home, home.catalog_path)
        ensure_materialized(home)

        providers = json.loads(home.catalog_path.read_text(encoding="utf-8"))
        entries = [p for p in providers.get("providers", []) if p.get("id") == "groq"]
        assert len(entries) == 1, "duplicate groq after refresh"
        assert entries[0]["baseUrl"] == "http://my-proxy.local/v1"
        assert entries[0]["source"] == "user"

    def test_edited_builtin_model_pricing_survives_seed_bump(self, temp_dir: Path):
        home = StorageHome(temp_dir)
        ensure_materialized(home)
        builtin_gemini_models = [
            m
            for provider in json.loads(home.catalog_path.read_text(encoding="utf-8")).get(
                "providers", []
            )
            for m in provider.get("models", [])
            if provider.get("id") == "gemini"
        ]
        assert builtin_gemini_models, "expected seeded gemini models"
        target = builtin_gemini_models[0]
        target_id = target["id"]

        upsert_model(
            home,
            {
                "providerId": "gemini",
                "id": target_id,
                "name": target.get("name"),
                "pricing": {"input": 9.0, "output": 42.0},
            },
        )
        self._age_seed(home, home.catalog_path)
        ensure_materialized(home)

        models_doc = json.loads(home.catalog_path.read_text(encoding="utf-8"))
        matches = [
            m
            for provider in models_doc.get("providers", [])
            for m in provider.get("models", [])
            if isinstance(m, dict) and m.get("id") == target_id
        ]
        assert len(matches) == 1, "duplicate model id after refresh"
        assert matches[0]["pricing"]["input"] == 9.0
        assert matches[0]["pricing"]["output"] == 42.0


class TestCheckpointInline:
    async def test_checkpoint_is_latest_wins_inside_session_file(self, temp_dir: Path):
        home = StorageHome(temp_dir)
        ensure_materialized(home)
        repo = session_store_mod.FileCheckpointRepository(home)
        srepo = FileSessionRepository(home)
        s = await srepo.create(Session(id="sess-ckpt", title="t", workspace_root=str(temp_dir)))

        for i in range(3):
            await repo.create(s.id, snapshot_data={"i": i})

        latest = await repo.get_latest(s.id)
        assert latest is not None
        assert latest["snapshot_data"] == {"i": 2}
        # Append-only stream; the FOLD decides latest-wins.
        path = session_store_mod.locate(home, s.id)
        cps = [r["id"] for r in read_jsonl(path) if r.get("t") == "checkpoint"]
        assert latest["id"] == cps[-1]


class TestSingleFileLayout:
    """One session = ONE jsonl under projects/<workspace-slug>/."""

    async def test_all_state_lands_in_one_file(self, temp_dir: Path):
        from server.storage.usage_store import FileTokenUsageRepository
        from server.storage.workspace_store import FileWorkspaceRepository

        home = StorageHome(temp_dir)
        ensure_materialized(home)
        ws_root = str(temp_dir / "myproj")
        srepo = FileSessionRepository(home)
        mrepo = FileMessageRepository(home)
        crepo = session_store_mod.FileCheckpointRepository(home)
        urepo = FileTokenUsageRepository(home)
        wrepo = FileWorkspaceRepository(home)

        s = await srepo.create(Session(id="sess-one", title="f", workspace_root=ws_root))
        await mrepo.append(Message(session_id=s.id, role="user", content="hi"))
        await crepo.create(s.id, snapshot_data={"step": 1})
        await urepo.record(
            s.id, provider="groq", model="m", total_tokens=10, context_window=1000, step_index=-1
        )
        await wrepo.upsert(s.id, "a.txt", "h", 5, 1, 0, 0.0, 0.0)

        project_dir = home.project_dir(ws_root)
        files = list(project_dir.iterdir())
        assert [p.name for p in files] == ["sess-one.jsonl"]
        kinds = [r["t"] for r in read_jsonl(files[0])]
        assert kinds[0] == "header"
        for kind in ("msg", "checkpoint", "usage", "wsfile"):
            assert kind in kinds
        # No stray per-session artifacts anywhere else.
        strays = [
            p for p in home.projects_dir.rglob("*") if p.is_file() and p.name != "sess-one.jsonl"
        ]
        assert strays == []

    async def test_projects_are_grouped_by_workspace(self, temp_dir: Path):
        home = StorageHome(temp_dir)
        ensure_materialized(home)
        srepo = FileSessionRepository(home)
        root_a = str(temp_dir / "alpha")
        root_b = str(temp_dir / "beta")
        await srepo.create(Session(id="sess-a", title="a", workspace_root=root_a))
        await srepo.create(Session(id="sess-b", title="b", workspace_root=root_b))
        assert (home.project_dir(root_a) / "sess-a.jsonl").exists()
        assert (home.project_dir(root_b) / "sess-b.jsonl").exists()

    async def test_delete_removes_the_single_file(self, temp_dir: Path):
        home = StorageHome(temp_dir)
        ensure_materialized(home)
        srepo = FileSessionRepository(home)
        s = await srepo.create(Session(id="sess-del", title="d", workspace_root=str(temp_dir)))
        assert await srepo.delete(s.id) is True
        assert not home.session_file("sess-del", str(temp_dir)).exists()
        assert await srepo.get(s.id) is None


class TestSeedIdempotence:
    def test_double_materialization_is_stable(self, temp_dir: Path):
        home = StorageHome(temp_dir)
        ensure_materialized(home)
        catalog_before = home.catalog_path.read_text(encoding="utf-8")
        ensure_materialized(home)
        assert home.catalog_path.read_text(encoding="utf-8") == catalog_before

    def test_user_entries_survive_refresh(self, temp_dir: Path):
        from server.storage import catalog_store

        home = StorageHome(temp_dir)
        ensure_materialized(home)
        upsert_provider(
            home,
            {
                "id": "my_vendor",
                "name": "My Vendor",
                "adapter": "openai_compatible",
                "baseUrl": "http://localhost:9999/v1",
                "requiresApiKey": False,
                "firstClass": False,
                "customFlow": True,
            },
        )
        upsert_model(
            home,
            {
                "providerId": "my_vendor",
                "id": "my-model",
                "name": "My Model",
                "contextWindow": 8192,
            },
        )
        # Force a refresh by pretending an older seed is on disk.
        doc = read_json(home.catalog_path, {})
        doc["seedVersion"] = catalog_store.builtin_seed.SEED_VERSION - 1
        write_json_atomic(home.catalog_path, doc)

        ensure_materialized(home)
        providers = catalog_store.read_providers(home)
        assert "my_vendor" in providers, "user provider lost during builtin refresh"
        model = None
        for entry in catalog_store.read_model_entries(home).values():
            if entry.get("id") == "my-model":
                model = entry
                break
        assert model is not None, "user model lost during builtin refresh"


class TestProfileStore:
    async def test_api_keys_live_only_in_profile(self, temp_dir: Path):
        from server.storage.provider_config import save_provider_config

        home = StorageHome(temp_dir)
        ensure_materialized(home)
        profile = load_profile(home)
        set_api_key(profile, "gemini", "AQ.secret123")
        save_profile(home, profile)
        save_provider_config(
            home,
            provider="groq",
            api_key="gsk_abc",
            model="llama-3.3-70b-versatile",
        )
        for name in ("zenith_catalog.json",):
            assert "AQ.secret123" not in (home.root / name).read_text(encoding="utf-8")
            assert "gsk_abc" not in (home.root / name).read_text(encoding="utf-8")
        # Legacy split files must not be recreated.
        assert not (home.root / "providers.json").exists()
        assert not (home.root / "models.json").exists()
        saved = load_profile(home)
        assert saved["apiKeys"]["gemini"] == "AQ.secret123"

    async def test_message_counts_track_user_roles(self, temp_dir: Path):
        home = StorageHome(temp_dir)
        ensure_materialized(home)
        srepo = FileSessionRepository(home)
        mrepo = FileMessageRepository(home)
        s = await srepo.create(Session(id="sess-counts", title="t"))
        await mrepo.append(Message(session_id=s.id, role="user", content="u1"))
        await mrepo.append(Message(session_id=s.id, role="assistant", content="a1"))
        await mrepo.append(Message(session_id=s.id, role="tool", content="tool out"))
        got = await srepo.get(s.id)
        assert got is not None
        assert got.message_count == 1  # only user role bumps count (DB parity)

    async def test_summaries_hide_empty_sessions(self, temp_dir: Path):
        home = StorageHome(temp_dir)
        ensure_materialized(home)
        srepo = FileSessionRepository(home)
        mrepo = FileMessageRepository(home)
        empty = await srepo.create(Session(id="sess-empty", title="Empty"))
        full = await srepo.create(Session(id="sess-full", title="Full"))
        await mrepo.append(Message(session_id=full.id, role="user", content="hi"))
        rows = await srepo.get_summaries(limit=10)
        ids = {r["id"] for r in rows}
        assert empty.id not in ids
        assert full.id in ids

    async def test_summaries_use_tail_fold_without_full_rescan(self, temp_dir: Path, monkeypatch):
        # Listing reads only the file tail (stats/meta records); it must not
        # run a full snapshot fold per session.
        home = StorageHome(temp_dir)
        ensure_materialized(home)
        srepo = FileSessionRepository(home)
        mrepo = FileMessageRepository(home)
        s = await srepo.create(
            Session(id="sess-fast-list", title="f", workspace_root=str(temp_dir))
        )
        await mrepo.append(Message(session_id=s.id, role="user", content="hi"))

        from server.storage import session_file as session_file_mod

        calls: list[str] = []

        real = session_file_mod.load_snapshot

        def counting(home_, sid):
            calls.append(sid)
            return real(home_, sid)

        monkeypatch.setattr(session_store_mod, "load_snapshot", counting)
        rows = await srepo.get_summaries(limit=10)
        assert any(r["id"] == s.id for r in rows)
        assert calls == [], "get_summaries must use the tail path, not full folds"

    async def test_compaction_preserves_tail(self, temp_dir: Path):
        home = StorageHome(temp_dir)
        ensure_materialized(home)
        srepo = FileSessionRepository(home)
        mrepo = FileMessageRepository(home)
        s = await srepo.create(Session(id="sess-compaction", title="c"))
        ids = []
        for i in range(4):
            m = await mrepo.append(
                Message(session_id=s.id, role="user", content=f"m{i}", token_count=i)
            )
            ids.append(m.id)
        deleted = await mrepo.compact_history(
            s.id, metadata={"summary": "folded"}, delete_ids=ids[:2]
        )
        assert deleted == 2
        history = await mrepo.get_by_session(s.id)
        assert [h.content for h in history] == ["m2", "m3"]
        md = await srepo.get_metadata(s.id)
        assert md == {"summary": "folded"}
