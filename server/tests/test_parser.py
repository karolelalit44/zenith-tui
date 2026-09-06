from server.providers.parser import UnifiedResponseFormatter, parse_tool_calls


def test_parse_tool_calls_clean_json():
    text = '```tool\n{"tool": "file_write", "params": {"filepath": "foo.py", "content": "print(1)"}}\n```'
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "file_write"
    assert calls[0]["params"]["path"] == "foo.py"


def test_parse_tool_calls_camelcase_filepath():
    text = '```json\n{"tool": "file_write", "params": {"filePath": "stringCounter.ts", "content": "class StringCounter {}"}}\n```'
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "file_write"
    assert calls[0]["params"]["path"] == "stringCounter.ts"
    assert calls[0]["params"]["content"] == "class StringCounter {}"


def test_parse_tool_calls_no_duplicate_span():
    text = 'Here is the tool call:\n\n```json\n{"tool": "file_write", "params": {"filePath": "D:/vdo/code/backend/stringCounter.ts", "content": "test"}}\n```'
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "file_write"
    assert calls[0]["params"]["path"] == "D:/vdo/code/backend/stringCounter.ts"


def test_parse_tool_calls_dirty_multiline_json():
    text = '```tool\n{"tool": "file_write", "params": {"filepath": "D:/vdo/code/backend/string_analyzer.py", "content": """\nString Analyzer - Analyzes a hardcoded string\ndef count_vowels(text):\n    return sum(1 for c in text if c in \'aeiou\')\n"""}}\n```'
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "file_write"
    assert "path" in calls[0]["params"]
    assert "count_vowels" in calls[0]["params"]["content"]


def test_unified_response_formatter():
    raw_text = 'I will write the file.\n\n```tool\n{"tool": "file_write", "params": {"filepath": "a.txt", "content": "hello"}}\n```\nCommand: cd backend && python a.py\nOutput: ok'
    clean, calls = UnifiedResponseFormatter.process_response(raw_text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "file_write"
    assert calls[0]["params"]["path"] == "a.txt"
    assert "```tool" not in clean
    assert "Command:" not in clean
    assert "I will write the file." in clean


def test_parse_xml_tool_call():
    raw_text = "I'll inspect the files.<tool_call>glob<arg_key>pattern</arg_key><arg_value>/*</arg_value><arg_key>depth</arg_key><arg_value>3</arg_value></tool_call>"
    clean, calls = UnifiedResponseFormatter.process_response(raw_text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "glob"
    assert calls[0]["params"]["pattern"] == "/*"
    assert calls[0]["params"]["depth"] == "3"
    assert "<tool_call>" not in clean
    assert "I'll inspect the files." in clean


def test_parse_multiple_objects_in_single_fence():
    text = (
        '```tool\n{"tool": "get_tool_definition", "params": {"tool_name": "file_write"}}\n'
        '{"tool": "file_write", "params": {"path": "c.txt", "content": "c"}}\n```'
    )
    calls = parse_tool_calls(text)
    assert [c["tool"] for c in calls] == ["get_tool_definition", "file_write"]
    assert calls[1]["params"]["path"] == "c.txt"
    assert calls[1]["params"]["content"] == "c"


def test_parse_multiple_same_tool_objects_in_single_fence():
    text = (
        '```tool\n{"tool": "file_write", "params": {"path": "a.txt", "content": "a"}}\n'
        '{"tool": "file_write", "params": {"path": "b.txt", "content": "b"}}\n```'
    )
    calls = parse_tool_calls(text)
    assert len(calls) == 2
    assert calls[0]["params"]["path"] == "a.txt"
    assert calls[1]["params"]["path"] == "b.txt"


def test_parse_bracket_tool_call():
    raw_text = 'Let me search the files: [Tool: glob pattern="*.py"]'
    clean, calls = UnifiedResponseFormatter.process_response(raw_text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "glob"
    assert calls[0]["params"]["pattern"] == "*.py"
    assert "[Tool: glob" not in clean
    assert "Let me search the files:" in clean


def test_parse_bracket_ignores_tool_result():
    raw_text = 'Previous step output:\n[Tool: glob | Status: SUCCESS]\nFound 3 files'
    clean, calls = UnifiedResponseFormatter.process_response(raw_text)
    assert len(calls) == 0
    assert "[Tool: glob | Status: SUCCESS]" in clean
    assert "Found 3 files" in clean


