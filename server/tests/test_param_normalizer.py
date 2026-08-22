from server.toolkit.param_normalizer import canonicalize_path_values, normalize_file_params


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


def test_filepath_key_tools_keep_filepath():
    for tool in ("multi_edit", "lsp_definition", "lsp_diagnostics", "lsp_rename"):
        res = normalize_file_params({"path": "a.py"}, tool_name=tool)
        assert res.get("filepath") == "a.py", tool
        assert "path" not in res, tool
        res2 = normalize_file_params({"filepath": "a.py"}, tool_name=tool)
        assert res2.get("filepath") == "a.py", tool


def test_path_key_tools_keep_path():
    res = normalize_file_params({"filepath": "a.py"}, tool_name="file_write")
    assert res["path"] == "a.py"
    assert "filepath" not in res


def test_no_tool_name_defaults_to_path():
    assert normalize_file_params({"filepath": "a.txt"}) == {"path": "a.txt"}


def test_normalize_list_content_to_str():
    res = normalize_file_params({"path": "a.py", "content": ["line 1", "line 2"]})
    assert res["content"] == "line 1\nline 2"
    res_edit = normalize_file_params({"path": "a.py", "oldContent": ["old 1", "old 2"]})
    assert res_edit["old_content"] == "old 1\nold 2"


# ---------------------------------------------------------------------------
# QA-2: path-value canonicalization (dedup + loop detection)
# ---------------------------------------------------------------------------


def test_canonicalize_relative_and_absolute_paths_are_identical():
    ws = "/workspace"
    a = canonicalize_path_values({"path": "sessions.py"}, ws)
    b = canonicalize_path_values({"path": "./sessions.py"}, ws)
    c = canonicalize_path_values({"path": "/workspace/sessions.py"}, ws)
    assert a["path"] == b["path"] == c["path"]


def test_canonicalize_dotdot_equivalent_paths_are_identical():
    ws = "/workspace/src"
    a = canonicalize_path_values({"path": "sub/../a.py"}, ws)
    b = canonicalize_path_values({"path": "a.py"}, ws)
    assert a["path"] == b["path"]


def test_canonicalize_does_not_touch_non_path_params():
    ws = "/workspace"
    res = canonicalize_path_values({"content": "hello", "old_content": "hi"}, ws)
    assert res["content"] == "hello"
    assert res["old_content"] == "hi"


def test_canonicalize_command_param_untouched():
    ws = "/workspace"
    res = canonicalize_path_values({"command": "grep -r session ."}, ws)
    assert res["command"] == "grep -r session ."


def test_canonicalize_invalid_paths_never_collide_with_valid_or_each_other():
    ws = "/workspace"
    valid = canonicalize_path_values({"path": "a.py"}, ws)
    outside = canonicalize_path_values({"path": "/etc/passwd"}, ws)
    # An escaping path resolves to a stable invalid marker, distinct from valid.
    assert outside["path"] != valid["path"]
    assert outside["path"].startswith("\0nopath:")
    # Two different escaping paths stay distinct too.
    outside2 = canonicalize_path_values({"path": "/etc/hosts"}, ws)
    assert outside["path"] != outside2["path"]


def test_canonicalize_skips_without_workspace():
    # Without a workspace root there is no canonicalization — no-op.
    res = canonicalize_path_values({"path": "a.py"})
    assert res == {"path": "a.py"}
