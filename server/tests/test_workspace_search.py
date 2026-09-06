"""Module 16 additive interface-lock tests for server/workspace/search.py.

Tests the ripgrep-backed SearchMatch / RipgrepBackend primitive without
requiring the real ``rg`` binary by injecting a fake ``cmd_runner``.
"""

import asyncio

from server.workspace.search import RipgrepBackend, SearchMatch, _find_rg, _parse_grep_output


def test_search_match_fields():
    m = SearchMatch(path="src/a.py", line_number=3, text="def foo():")
    assert m.path == "src/a.py"
    assert m.line_number == 3
    assert m.text == "def foo():"


def test_parse_grep_output_typical():
    text = "src/a.py:3:def foo():\nsrc/a.py:4:    pass\n"
    matches = _parse_grep_output(text)
    assert len(matches) == 2
    assert matches[0].path == "src/a.py"
    assert matches[0].line_number == 3
    assert matches[0].text == "def foo():"


def test_parse_grep_output_malformed_and_windows_paths():
    text = (
        "not-a-valid-line\n"
        "C:/repo/file.py:12:print('hi')\n"
        "\n"
        "no-colon-here\n"
    )
    matches = _parse_grep_output(text)
    assert len(matches) == 1
    assert matches[0].path == "C:/repo/file.py"
    assert matches[0].line_number == 12
    assert matches[0].text == "print('hi')"


def test_parse_grep_output_content_with_colons():
    text = "src/a.py:5:print('a:b:c')\n"
    matches = _parse_grep_output(text)
    assert len(matches) == 1
    assert matches[0].path == "src/a.py"
    assert matches[0].line_number == 5
    assert matches[0].text == "print('a:b:c')"


async def _fake_runner(output: str, returncode: int = 0):
    async def runner(argv):
        return returncode, output, ""
    return runner


def test_grep_with_fake_runner():
    async def scenario():
        fake = await _fake_runner("src/a.py:3:def foo():\n")
        backend = RipgrepBackend(cmd_runner=fake)
        matches = await backend.grep("def foo", "src")
        assert len(matches) == 1
        assert matches[0].text == "def foo():"
    asyncio.run(scenario())


def test_grep_include_preserves_pattern_as_e_flag_and_adds_glob():
    """include must narrow which files are searched, not replace the pattern.

    Regression: previously ``grep("def foo", ".", include="*.py")`` emitted only a
    ``--glob`` and dropped the search pattern entirely — a logic bug. Verify the argv
    contains ``-e <pattern>`` AND ``--glob <include>`` together.
    """

    captured = {}

    async def runner(argv):
        captured["argv"] = argv
        return 0, "src/a.py:3:def foo():\n", ""

    async def scenario():
        backend = RipgrepBackend(cmd_runner=runner)
        matches = await backend.grep("def foo", ".", include="*.py")
        assert len(matches) == 1
        assert "-e" in captured["argv"]
        assert "def foo" in captured["argv"]
        assert "--glob" in captured["argv"]
        assert "*.py" in captured["argv"]

    asyncio.run(scenario())


def test_grep_max_results_caps_output():
    async def scenario():
        fake = await _fake_runner(
            "src/a.py:1:x\nsrc/a.py:2:x\nsrc/a.py:3:x\nsrc/a.py:4:x\n"
        )
        backend = RipgrepBackend(cmd_runner=fake, max_results=2)
        matches = await backend.grep("x", "src")
        assert len(matches) == 2
        assert matches[0].line_number == 1
        assert matches[1].line_number == 2
    asyncio.run(scenario())


def test_glob_with_fake_runner():
    async def scenario():
        fake = await _fake_runner("src/a.py\nsrc/b.py\n")
        backend = RipgrepBackend(cmd_runner=fake)
        files = await backend.glob("*.py", "src")
        assert files == ["src/a.py", "src/b.py"]
    asyncio.run(scenario())


def test_error_returns_empty():
    async def scenario():
        fake = await _fake_runner("", returncode=2)
        backend = RipgrepBackend(cmd_runner=fake)
        assert await backend.grep("needle", "src") == []
        assert await backend.glob("*.py", "src") == []
    asyncio.run(scenario())


def test_find_rg_cached():
    assert callable(_find_rg)
    first = _find_rg()
    second = _find_rg()
    assert first is second
