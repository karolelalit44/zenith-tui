"""Regression tests for user_profile.json write serialization.

Review finding #1: profile read-modify-write cycles used to be guarded by
an asyncio.Lock only, so sync ``def`` FastAPI endpoints running in the
threadpool raced event-loop writers and could silently drop an API key.
PROFILE_LOCK now serializes every profile write process-wide, regardless
of which thread or loop issues it.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from server.storage import StorageHome, ensure_materialized
from server.storage.profile_store import (
    load_profile,
    set_api_key,
    update_preferences,
    validate_preferences,
)
from server.storage.provider_config import save_provider_config


class TestConcurrentProfileWriters:
    async def _race(self, temp_dir: Path, fresh_home_per_call: bool) -> dict:
        home = StorageHome(temp_dir)
        ensure_materialized(home)
        n_keys = 12

        def target() -> StorageHome:
            return StorageHome(temp_dir) if fresh_home_per_call else home

        def key_writer(i: int) -> None:
            save_provider_config(
                target(),
                provider=f"prov_{i}",
                api_key=f"sk-secret-{i}",
            )

        def theme_writer(i: int) -> None:
            update_preferences(target(), {"theme": f"theme-{i}"})

        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=n_keys * 2) as pool:
            futures = [loop.run_in_executor(pool, key_writer, i) for i in range(n_keys)]
            # Interleave event-loop-issued writes with threadpool-issued
            # ones touching the same keys — exactly the old losing
            # combination.
            for i in range(n_keys):
                futures.append(loop.run_in_executor(pool, theme_writer, i))
                theme_writer(i)
                await asyncio.sleep(0)
            await asyncio.gather(*futures)

        return load_profile(home)

    async def test_threadpool_and_loop_writers_lose_nothing(self, temp_dir: Path):
        profile = await self._race(temp_dir, fresh_home_per_call=False)
        self._assert_everything_survived(profile)

    async def test_independent_home_instances_lose_nothing(self, temp_dir: Path):
        # The API layer constructs its own StorageHome per request; the
        # lock must still serialize across instances.
        profile = await self._race(temp_dir, fresh_home_per_call=True)
        self._assert_everything_survived(profile)

    @staticmethod
    def _assert_everything_survived(profile: dict) -> None:
        keys = profile.get("apiKeys") or {}
        missing = [i for i in range(12) if keys.get(f"prov_{i}") != f"sk-secret-{i}"]
        assert missing == [], f"lost API keys for writers {missing}"
        theme = (profile.get("preferences") or {}).get("theme", "")
        assert theme.startswith("theme-"), f"theme not any writer's value: {theme!r}"


class TestPreferenceValidation:
    """update_preferences rejects junk instead of persisting it (review P3)."""

    def _home(self, temp_dir: Path) -> StorageHome:
        home = StorageHome(temp_dir / self.__class__.__name__)
        ensure_materialized(home)
        return home

    def test_unknown_key_rejected(self, temp_dir: Path):
        with pytest.raises(ValueError, match="unsupported preference"):
            validate_preferences({"notARealKey": "x"})

    def test_wrong_type_rejected(self, temp_dir: Path):
        with pytest.raises(ValueError):
            validate_preferences({"theme": ["dark"]})
        with pytest.raises(ValueError):
            validate_preferences({"thinkingCollapsed": "yes"})

    def test_invalid_default_mode_rejected(self, temp_dir: Path):
        with pytest.raises(ValueError, match="defaultMode"):
            validate_preferences({"defaultMode": "yolo"})

    def test_oversized_list_rejected(self, temp_dir: Path):
        with pytest.raises(ValueError, match="unsupported preference"):
            validate_preferences({"modelRecent": [f"m{i}" for i in range(21)]})

    def test_blank_theme_rejected(self, temp_dir: Path):
        with pytest.raises(ValueError, match="theme"):
            validate_preferences({"theme": "   "})

    def test_valid_merge_persists(self, temp_dir: Path):
        home = self._home(temp_dir)
        prefs = update_preferences(home, {"theme": "nord", "defaultMode": "plan"})
        assert prefs["theme"] == "nord"
        assert prefs["defaultMode"] == "plan"
        reread = load_profile(home)["preferences"]
        assert reread["theme"] == "nord"

    def test_calm_mode_toggle_persists(self, temp_dir: Path):
        home = self._home(temp_dir)
        prefs = update_preferences(home, {"calmMode": True})
        assert prefs["calmMode"] is True
        assert load_profile(home)["preferences"]["calmMode"] is True

    def test_update_preferences_propagates_validation_errors(self, temp_dir: Path):
        home = self._home(temp_dir)
        with pytest.raises(ValueError):
            update_preferences(home, {"apikeys_are_junk": True})
        # Nothing was persisted.
        prefs = load_profile(home)["preferences"]
        assert "apikeys_are_junk" not in prefs
