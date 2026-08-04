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
    text = """Here is the tool call:

```json
{"tool": "file_write", "params": {"filePath": "D:/vdo/code/backend/stringCounter.ts", "content": "test"}}
```"""
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "file_write"
    assert calls[0]["params"]["path"] == "D:/vdo/code/backend/stringCounter.ts"


def test_parse_tool_calls_dirty_multiline_json():
    text = '''```tool
{"tool": "file_write", "params": {"filepath": "D:/vdo/code/backend/string_analyzer.py", "content": """
String Analyzer - Analyzes a hardcoded string
def count_vowels(text):
    return sum(1 for c in text if c in 'aeiou')
"""}}
```'''
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "file_write"
    assert "path" in calls[0]["params"]
    assert "count_vowels" in calls[0]["params"]["content"]


def test_unified_response_formatter():
    raw_text = 'I will write the file.\n\n```tool\n{"tool": "file_write", "params": {"filepath": "a.txt", "content": "hello"}}\n```\nCommand: cd backend && python a.py\nOutput: ok'
    clean, calls = UnifiedResponseFormatter.process_response(raw_text)
    # Text-based tool calls should now be parsed via parse_tool_calls fallback
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
