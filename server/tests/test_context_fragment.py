"""Module 06 additive interface-lock: ContextFragment (codex provenance-tagged slots).

The 5-tier scored context machinery stays for Phase 3; this guards the additive
ContextFragment model that build_messages will be re-wired onto.
"""

from server.agents.context import (
    ContentKind,
    ContextFragment,
    RenderedFragment,
    tagged_fragment,
)


class TestContextFragment:
    def test_render_wraps_in_markers(self):
        f = ContextFragment(role="env", body="OS: windows", markers=("<env>", "</env>"))
        r = f.render()
        assert isinstance(r, RenderedFragment)
        assert r.body == "<env>\nOS: windows\n</env>"
        assert r.content_kind is ContentKind.TEXT

    def test_no_markers_renders_plain_body(self):
        f = ContextFragment(role="history", body="line1\nline2")
        assert f.render().body == "line1\nline2"

    def test_lazy_callable_body_resolved_at_render(self):
        calls = []
        f = ContextFragment(role="x", body=lambda: (calls.append(1), "later")[1])
        assert callable(f.body)
        assert f.render().body == "later"
        assert calls == [1]

    def test_is_empty(self):
        assert ContextFragment(role="a", body="").is_empty is True
        assert ContextFragment(role="a", body="y").is_empty is False
        assert ContextFragment(role="a", body=lambda: "  ").is_empty is True


class TestTaggedFragment:
    def test_default_marker_scheme(self):
        f = tagged_fragment("summary", "folded history", ContentKind.SUMMARY)
        assert f.markers == ("<summary>", "</summary>")
        assert f.render().body == "<summary>\nfolded history\n</summary>"
        assert f.content_kind is ContentKind.SUMMARY

    def test_common_roles_are_explicit_slots(self):
        for role in ("env", "system_prompt", "repo_map", "skills", "instructions", "history"):
            f = tagged_fragment(role, "x")
            assert f.render().body.startswith(f"<{role}>")
