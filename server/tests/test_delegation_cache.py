"""Unit tests for the Repository Intelligence Cache and task signatures."""

from server.agents.delegation import (
    DELEGATION_CACHE_TTL_SECONDS,
    RepositoryIntelligenceCache,
    task_signature,
)
from server.agents.delegation.agent_result import AgentResult


def _result(summary: str = "found it") -> AgentResult:
    return AgentResult(task_id="t", agent_id="codebase-scout", summary=summary)


class TestSignature:
    def test_deterministic_and_normalized(self):
        a = task_signature("  Find   the SESSION store ", "codebase-scout", "sess-1")
        b = task_signature("find the session store", "codebase-scout", "sess-1")
        assert a == b
        assert a == task_signature("find the session store", "codebase-scout", "sess-1")

    def test_varies_by_agent_and_session(self):
        sig = task_signature("objective", "codebase-scout", "s1")
        assert sig != task_signature("objective", "other", "s1")
        assert sig != task_signature("objective", "codebase-scout", "s2")


class TestCache:
    def test_default_ttl_matches_spec(self):
        assert DELEGATION_CACHE_TTL_SECONDS == 300

    def test_miss_returns_none(self):
        cache = RepositoryIntelligenceCache()
        assert cache.get("nope") is None

    def test_hit_within_ttl(self):
        cache = RepositoryIntelligenceCache()
        cache.put("sig", _result())
        hit = cache.get("sig")
        assert hit is not None
        assert hit.summary == "found it"
        # Stored result must not be mutated by later reads/copies.
        hit.summary = "tampered"
        assert cache.get("sig").summary == "found it"

    def test_ttl_expiry(self):
        cache = RepositoryIntelligenceCache(ttl_seconds=0.01)
        cache.put("sig", _result())
        import time

        time.sleep(0.03)
        assert cache.get("sig") is None

    def test_overwrite_same_signature(self):
        cache = RepositoryIntelligenceCache()
        cache.put("sig", _result("first"))
        cache.put("sig", _result("second"))
        assert cache.get("sig").summary == "second"

    def test_clear(self):
        cache = RepositoryIntelligenceCache()
        cache.put("sig", _result())
        cache.clear()
        assert cache.get("sig") is None
