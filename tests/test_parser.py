from zenith.providers.parser import parse_tool_calls, clean_tool_text, UnifiedResponseFormatter

def test_parse_tool_calls_clean_json():
    text = '```tool\n{"tool": "file_write", "params": {"filepath": "foo.py", "content": "print(1)"}}\n```'
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "file_write"
    assert calls[0]["params"]["filepath"] == "foo.py"

def test_parse_tool_calls_dirty_multiline_json():
    text = '''```tool
{"tool": "file_write", "params": {"filepath": "D:/vdo/code/zenith/string_analyzer.py", "content": """
String Analyzer - Analyzes a hardcoded string
def count_vowels(text):
    return sum(1 for c in text if c in 'aeiou')
"""}}
```'''
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "file_write"
    assert "filepath" in calls[0]["params"]
    assert "count_vowels" in calls[0]["params"]["content"]

def test_unified_response_formatter():
    raw_text = 'I will write the file.\n\n```tool\n{"tool": "file_write", "params": {"filepath": "a.txt", "content": "hello"}}\n```\nCommand: cd zenith && python a.py\nOutput: ok'
    clean, calls = UnifiedResponseFormatter.process_response(raw_text)
    assert len(calls) == 1
    assert "```tool" not in clean
    assert "Command:" not in clean
    assert "I will write the file." in clean
