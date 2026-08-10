"""Task 13 A2/RC1/RC4: durable session write-registry.

Records come only from real write/edit events; byte-identical re-writes of the
model's own prior work are blocked across turns of the same session.
"""

from server.agents.session_workspace import (
    is_identical_replay,
    known_files,
    record_edit,
    record_write,
    reset_session,
)


def test_empty_session_has_no_files():
    reset_session("s1")
    assert known_files("s1") == {}
    assert is_identical_replay("s1", "a.py", "x") is False


def test_record_write_then_identical_replay_detected():
    reset_session("s2")
    record_write("s2", "weather.py", "def main(): pass\n")
    assert is_identical_replay("s2", "weather.py", "def main(): pass\n") is True
    assert is_identical_replay("s2", "weather.py", "def main(): return\n") is False
    assert is_identical_replay("s2", "other.py", "def main(): pass\n") is False


def test_later_write_updates_hash():
    reset_session("s3")
    record_write("s3", "a.py", "v1")
    record_write("s3", "a.py", "v2")
    assert is_identical_replay("s3", "a.py", "v1") is False
    assert is_identical_replay("s3", "a.py", "v2") is True


def test_record_edit_keeps_last_known_hash():
    reset_session("s4")
    record_write("s4", "a.py", "v1")
    record_edit("s4", "a.py")
    # The edit changed the file on disk but the registry keeps the last written
    # hash; a re-write of the ORIGINAL content is still a replay.
    assert is_identical_replay("s4", "a.py", "v1") is True
    rec = known_files("s4")["a.py"]
    assert rec.edits == 1 and rec.writes == 0


def test_sessions_are_isolated():
    reset_session("sA")
    reset_session("sB")
    record_write("sA", "a.py", "content")
    assert is_identical_replay("sB", "a.py", "content") is False
    assert known_files("sB") == {}


def test_reset_clears_session():
    reset_session("s5")
    record_write("s5", "a.py", "content")
    reset_session("s5")
    assert known_files("s5") == {}
