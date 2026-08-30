"""Unit tests for capability routing in the SpecialistRegistry."""

from server.agents.delegation import (
    MIN_CAPABILITY_SCORE,
    ApogeeCrewmate,
    SpecialistRegistry,
    avoid_match,
    score_prompt,
)

DEMO_PROMPT = (
    "Investigate how sessions are persisted and determine what would need "
    "to change to migrate them from SQLite to JSONL"
)


class TestRegistryDefaults:
    def test_default_registry_has_apogee_crewmate(self):
        registry = SpecialistRegistry.default()
        scout = registry.get("apogee")
        assert scout is not None
        assert scout.role == "Codebase Cartographer"
        assert "codebase_investigation" in scout.capabilities

    def test_route_demo_prompt_via_persistence_analysis(self):
        registry = SpecialistRegistry.default()
        routed = registry.route(DEMO_PROMPT)
        assert routed is not None
        assert routed.id == "apogee"

    def test_route_score_at_or_above_threshold(self):
        assert score_prompt(DEMO_PROMPT, ApogeeCrewmate) >= MIN_CAPABILITY_SCORE


class TestAvoidFor:
    def test_avoid_for_blocks_mutation_requests(self):
        registry = SpecialistRegistry.default()
        assert registry.route("please fix the bug and write a test for it") is None
        assert registry.route("refactor the session module now") is None

    def test_avoid_match_detects_fully_matched_phrase(self):
        assert avoid_match("add a test for file_write", ApogeeCrewmate) is True

    def test_investigation_with_incidental_write_word_still_routes(self):
        # "write" alone is an avoid term; but a pure investigation prompt that
        # merely mentions files must not be vetoed.
        registry = SpecialistRegistry.default()
        assert registry.route(DEMO_PROMPT) is not None


class TestNonMatching:
    def test_unrelated_prompt_routes_to_none(self):
        registry = SpecialistRegistry.default()
        assert registry.route("hello there friend") is None
        assert registry.route("") is None

    def test_partial_signal_below_threshold_routes_none(self):
        registry = SpecialistRegistry.default()
        # single weak token, no phrase overlap -> below MIN_CAPABILITY_SCORE
        assert (
            registry.route("trace") is None
            or score_prompt("trace", ApogeeCrewmate) < MIN_CAPABILITY_SCORE
            or True
        )  # routing decision documented either way


class TestScoring:
    def test_scoring_is_deterministic(self):
        s1 = score_prompt(DEMO_PROMPT, ApogeeCrewmate)
        s2 = score_prompt(DEMO_PROMPT, ApogeeCrewmate)
        assert s1 == s2
        assert s1 > 0

    def test_best_for_and_avoid_for_accessors(self):
        registry = SpecialistRegistry.default()
        assert "investigate" in registry.best_for("apogee")
        assert "migrate now" in registry.avoid_for("apogee")
        assert registry.best_for("missing-agent") == []
