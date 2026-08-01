"""Tests for parameter normalizer module."""

from server.toolkit.param_normalizer import normalize_file_params


def test_normalize_path_aliases():
    assert normalize_file_params({"filePath": "a.txt"}) == {"path": "a.txt"}
    assert normalize_file_params({"file_path": "a.txt"}) == {"path": "a.txt"}
    assert normalize_file_params({"targetFile": "a.txt"}) == {"path": "a.txt"}
    assert normalize_file_params({"target_path": "a.txt"}) == {"path": "a.txt"}
    assert normalize_file_params({"filename": "a.txt"}) == {"path": "a.txt"}
    assert normalize_file_params({"dest": "a.txt"}) == {"path": "a.txt"}


def test_normalize_content_aliases():
    assert normalize_file_params({"search": "a", "replace": "b"}) == {
        "old_content": "a",
        "new_content": "b",
    }
    assert normalize_file_params({"oldContent": "a", "newContent": "b"}) == {
        "old_content": "a",
        "new_content": "b",
    }


def test_normalize_command_and_pattern():
    assert normalize_file_params({"cmd": "echo 1"}) == {"command": "echo 1"}
    assert normalize_file_params({"query": "*.py"}) == {"pattern": "*.py"}


def test_canonical_keys_preserved():
    res = normalize_file_params({"path": "a.txt"})
    assert res["path"] == "a.txt"


def test_normalize_list_content_to_str():
    res = normalize_file_params({"path": "a.py", "content": ["line 1", "line 2"]})
    assert res["content"] == "line 1\nline 2"

    res_edit = normalize_file_params({"path": "a.py", "oldContent": ["old 1", "old 2"]})
    assert res_edit["old_content"] == "old 1\nold 2"

