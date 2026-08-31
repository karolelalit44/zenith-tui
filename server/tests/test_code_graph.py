"""Tests for the tree-sitter code graph queries (workspace/graph_queries.py).

Note: module 16's Phase-1 additive surface is the ripgrep-backed
``workspace/search.py`` (tested in test_workspace_search.py). The tree-sitter
code graph is the (Phase-3-removal) legacy consumer; these tests lock its
behaviour while it is still the live repo-map/code-graph stack.
"""

import pytest

from server.workspace.graph_queries import CodeGraph, clear_code_graph_cache
from server.workspace.ignore import clear_matcher_cache


@pytest.fixture(autouse=True)
def _clean_caches():
    clear_matcher_cache()
    clear_code_graph_cache()
    yield
    clear_matcher_cache()
    clear_code_graph_cache()


@pytest.fixture
def sample_repo(temp_dir):
    (temp_dir / "greeter.py").write_text(
        "def greet(name: str) -> str:\n"
        "    return f'hello {name}'\n\n"
        "def main():\n"
        "    print(greet('world'))\n"
    )
    (temp_dir / "app.py").write_text(
        "from greeter import greet\n\ndef run():\n    print(greet('zenith'))\n"
    )
    return temp_dir


class TestCodeGraph:
    def test_callers_find_references(self, sample_repo):
        graph = CodeGraph(str(sample_repo))
        callers = graph.callers("greet")
        files = {c["file"] for c in callers}
        assert "app.py" in files
        assert "greeter.py" in files  # main() references greet too

    def test_callers_unknown_symbol_is_empty(self, sample_repo):
        graph = CodeGraph(str(sample_repo))
        assert graph.callers("does_not_exist_anywhere_xyz") == []

    def test_outline_lists_definitions(self, sample_repo):
        graph = CodeGraph(str(sample_repo))
        outline = graph.outline("greeter.py")
        names = {d["name"] for d in outline}
        assert {"greet", "main"} <= names
        assert all(d["kind"] == "def" for d in outline)

    def test_outline_unknown_file_is_empty(self, sample_repo):
        graph = CodeGraph(str(sample_repo))
        assert graph.outline("missing.py") == []

    def test_outline_rejects_path_escape(self, sample_repo, tmp_path):
        graph = CodeGraph(str(sample_repo))
        outside = tmp_path / "outside.py"
        outside.write_text("x = 1")
        assert graph.outline(str(outside)) == []

    def test_blast_radius(self, sample_repo):
        graph = CodeGraph(str(sample_repo))
        result = graph.blast_radius("greet")
        assert result["symbol"] == "greet"
        assert result["caller_count"] >= 1
        assert "app.py" in result["affected_files"]

    def test_top_symbols_returns_ranked(self, sample_repo):
        graph = CodeGraph(str(sample_repo))
        tops = graph.top_symbols(limit=5)
        assert isinstance(tops, list)
        if tops:
            symbol, count = tops[0]
            assert isinstance(symbol, str)
            assert isinstance(count, int) and count >= 0
