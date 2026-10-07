"""Composed-context occupancy measurement.

Occupancy is the number that decides whether the next step fits in the window,
so every term it is missing is a term that lets a turn grow past the window
instead of compacting in time. Each test here covers one term.
"""

from server.agents.context import ContextManager
from server.config.constants import DEFAULT_CONTEXT_WINDOW, MIN_OUTPUT_TOKENS_FLOOR
from server.config.settings import AppSettings
from server.providers.token_counter import TokenCounter


def _write_call(payload_chars: int) -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "file_write",
                    "arguments": '{"path":"a.py","content":"' + "x" * payload_chars + '"}',
                },
            }
        ],
    }


class TestMessageTokenCounting:
    def test_tool_call_arguments_are_counted(self):
        """For the mutating tools the arguments *are* the payload.

        A file write bills its whole contents as input tokens. Counting only
        ``content`` reported every write the agent made as costing nothing.
        """
        counter = TokenCounter()
        small = counter.count_messages([_write_call(200)], "gpt-4")
        large = counter.count_messages([_write_call(8000)], "gpt-4")
        assert large > small * 10, f"write payload barely counted: {small} -> {large}"

    def test_list_content_is_measured_as_text_not_scaffolding(self):
        """Typed content parts are billed as their text, and measured as text.

        Passing the list straight to the encoder raises, and the heuristic
        fallback then divides the *part count* by the chars-per-token ratio — so
        a 4 000-character result reported as a handful of tokens.
        """
        counter = TokenCounter()
        as_parts = counter.count_messages(
            [{"role": "user", "content": [{"type": "text", "text": "x" * 4000}]}], "gpt-4"
        )
        as_text = counter.count_messages([{"role": "user", "content": "x" * 4000}], "gpt-4")
        assert as_parts >= as_text * 0.9, f"list content under-counted: {as_parts} vs {as_text}"

    def test_harness_metadata_is_not_counted(self):
        """Keys the loop attaches never reach the provider, so never count."""
        counter = TokenCounter()
        bare = [{"role": "user", "content": "hello"}]
        annotated = [
            {
                "role": "user",
                "content": "hello",
                "digest": "glob: ok",
                "tool_name": "glob",
                "salvage_digest": "glob: ok",
                "time": "compacted",
                "is_digested": True,
            }
        ]
        assert counter.count_messages(bare, "gpt-4") == counter.count_messages(annotated, "gpt-4")

    def test_non_dict_entries_are_skipped_not_fatal(self):
        counter = TokenCounter()
        assert counter.count_messages(["stray", {"role": "user", "content": "hi"}], "gpt-4") > 0


class TestAuxToolSchemaBudget:
    def test_aux_is_included_without_any_other_term(self):
        """The tool-schema block is on every request and in no message.

        Counting messages alone is therefore a lower bound, and a lower bound is
        exactly the kind of number that reads safe when it is not.
        """
        config = AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW, repo_map_enabled=False)
        ctx = ContextManager(config)
        messages = [{"role": "user", "content": "hi"}]
        before = ctx.usage_tokens(messages, "gpt-4")
        ctx.set_aux_tokens(5_000)
        assert ctx.usage_tokens(messages, "gpt-4") == before + 5_000

    def test_aux_is_never_negative(self):
        config = AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW, repo_map_enabled=False)
        ctx = ContextManager(config)
        ctx.set_aux_tokens(-100)
        assert ctx.usage_tokens([], "gpt-4") == TokenCounter().count_messages([], "gpt-4")


class TestGenerationCeiling:
    def test_ceiling_never_exceeds_the_window(self):
        """A ceiling larger than the whole window leaves the prompt no room.

        The provider then rejects or truncates the request instead of reserving
        space for the prompt that has to accompany the reply.
        """
        from server.config.constants import default_max_tokens_for_context

        for window in (4_000, 8_000, 32_000, 200_000, 1_000_000):
            assert default_max_tokens_for_context(window) <= window

    def test_ceiling_has_a_floor_on_a_window_that_can_afford_one(self):
        from server.config.constants import default_max_tokens_for_context

        assert default_max_tokens_for_context(64_000) >= MIN_OUTPUT_TOKENS_FLOOR

    def test_unknown_window_falls_back_to_the_configured_default(self):
        from server.config.constants import DEFAULT_LLM_MAX_TOKENS, default_max_tokens_for_context

        assert default_max_tokens_for_context(0) == DEFAULT_LLM_MAX_TOKENS


class TestSchemaTokensModeFiltering:
    def test_schema_tokens_filters_by_mode(self):
        """With a mode, only the schemas that request would carry are counted.

        Counting the whole active set bills schemas the request never sent.
        """
        from server.config.constants import BUILD_MODE
        from server.toolkit import create_default_registry
        from server.toolkit.resolver import SchemaResolver, build_mode_tool_seed

        registry = create_default_registry()
        # Seed with the whole registry: a mode filter is only observable when the
        # active set is genuinely larger than what one mode would send.
        resolver = SchemaResolver(
            registry, seed=build_mode_tool_seed(list(registry.list_tools()))
        )
        all_active = resolver.schema_tokens("gpt-4o")
        by_mode = resolver.schema_tokens("gpt-4o", mode=BUILD_MODE)
        assert all_active > 0
        assert 0 < by_mode <= all_active

    def test_schema_tokens_mode_is_a_strict_subset(self):
        """``mode`` must actually drop schemas, or the parameter is decorative."""
        from server.config.constants import BUILD_MODE, PLAN_MODE
        from server.toolkit import create_default_registry
        from server.toolkit.resolver import SchemaResolver, build_mode_tool_seed

        registry = create_default_registry()
        resolver = SchemaResolver(
            registry, seed=build_mode_tool_seed(list(registry.list_tools()))
        )
        active_names = set(resolver._active)
        build_names = {s["name"] for s in resolver.schemas(BUILD_MODE)}
        plan_names = {s["name"] for s in resolver.schemas(PLAN_MODE)}

        # Every mode offers a subset of the active set...
        assert build_names <= active_names
        assert plan_names <= active_names
        # ...and plan drops the build-only tools, so mode is a real filter.
        assert plan_names < build_names
        assert not (plan_names & {"bash", "file_delete", "job_kill"})
        # Without the mode the whole active set is billed; with one it is not.
        assert resolver.schema_tokens("gpt-4o", mode=PLAN_MODE) > 0
        assert resolver.schema_tokens("gpt-4o", mode=PLAN_MODE) < resolver.schema_tokens("gpt-4o")
        assert (
            resolver.schema_tokens("gpt-4o", mode=PLAN_MODE)
            < resolver.schema_tokens("gpt-4o", mode=BUILD_MODE)
        )

    def test_schema_tokens_is_memoised_per_active_set(self, monkeypatch):
        """A cache must avoid recomputation, not merely return the same number."""
        import server.toolkit.resolver as resolver_mod
        from server.toolkit import create_default_registry
        from server.toolkit.resolver import SchemaResolver

        calls: list[str] = []
        real = resolver_mod.estimate_tool_schema_tokens

        def counting(schema, description, model):
            calls.append(model)
            return real(schema, description, model)

        monkeypatch.setattr(resolver_mod, "estimate_tool_schema_tokens", counting)

        registry = create_default_registry()
        resolver = SchemaResolver(registry, seed=["file_read", "glob"])
        first = resolver.schema_tokens("gpt-4o")
        assert first > 0
        warmed = len(calls)
        assert warmed > 0

        assert resolver.schema_tokens("gpt-4o") == first
        assert len(calls) == warmed, "second call for an unchanged active set must hit the cache"

        assert resolver.request_tool("file_delete") is True
        resolver.schema_tokens("gpt-4o")
        assert len(calls) > warmed, "a changed active set must invalidate the cache"
        assert resolver._schema_token_cache is not None