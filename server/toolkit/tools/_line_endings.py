"""Byte-exact line handling for in-place file mutation.

A targeted edit must not round-trip a whole file through a normalized string.
Doing so rewrites every line ending in the file, so a one-line change becomes a
whole-file diff and line-ending-sensitive tooling breaks. The helpers here split
text into *physical* lines that keep their original terminators and splice a
replacement into a line range, leaving every untouched character verbatim.

Matching may still be done on CRLF-normalized text (the model sends LF while the
file holds CRLF); :func:`crlf_normalized_with_offsets` returns the offset map
needed to translate a match back onto the original text.
"""

from __future__ import annotations

_CRLF = "\r\n"


def split_physical_lines(text: str) -> list[str]:
    """Split *text* into lines that retain their original terminators."""
    return text.splitlines(keepends=True)


def line_body(line: str) -> str:
    """*line*'s content with any trailing ``\\r\\n`` / ``\\n`` / ``\\r`` removed."""
    if line.endswith(_CRLF):
        return line[:-2]
    if line.endswith(("\n", "\r")):
        return line[:-1]
    return line


def line_terminator(line: str) -> str:
    """The terminator *line* ends with, or ``""`` when it ends at EOF."""
    if line.endswith(_CRLF):
        return _CRLF
    if line.endswith("\n"):
        return "\n"
    if line.endswith("\r"):
        return "\r"
    return ""


def dominant_terminator(lines: list[str]) -> str:
    """The line ending *lines* use most often; ``"\\n"`` when they use none."""
    crlf = sum(1 for line in lines if line.endswith(_CRLF))
    return _CRLF if crlf > len(lines) - crlf else "\n"


def local_terminator(text: str, index: int) -> str:
    """The line ending in force at *index*.

    The terminator closing the line that contains *index*, else the previous
    line's, else the file's dominant ending, else ``"\\n"``. Used to re-terminate
    replacement text so one spliced edit cannot restyle the rest of the file.
    """
    line_start = text.rfind("\n", 0, index) + 1
    line_end = text.find("\n", index)
    if line_end != -1:
        return _CRLF if line_end > line_start and text[line_end - 1] == "\r" else "\n"
    if line_start >= 2 and text[line_start - 1] == "\n" and text[line_start - 2] == "\r":
        return _CRLF
    if line_start >= 1 and text[line_start - 1] == "\n":
        return "\n"
    return dominant_terminator(split_physical_lines(text))


def terminated(new_text: str, term: str, *, tail_newline: bool) -> list[str]:
    """Split *new_text* into physical lines carrying *term*.

    Terminators already present in *new_text* are transport, not content: they
    are replaced by *term* so the result depends only on the destination file
    and never on how the caller happened to encode the new text. A trailing
    terminator inside *new_text* is an explicit request to close the last line
    and is always honoured; otherwise ``tail_newline`` decides, letting the
    caller mirror the destination's EOF state instead of inventing a newline.
    """
    if new_text == "":
        return []
    lines = split_physical_lines(new_text)
    close_last = tail_newline or line_terminator(lines[-1]) != ""
    out: list[str] = []
    for i, line in enumerate(lines):
        body = line_body(line)
        out.append(body + term if i < len(lines) - 1 or close_last else body)
    return out


def crlf_normalized_with_offsets(text: str) -> tuple[str, list[int]]:
    """Return ``text`` with CRLF collapsed to LF, plus each char's source index.

    ``offsets[i]`` is the index in *text* of the character at normalized position
    ``i``. The two strings differ only by dropped ``"\\r"`` characters, so a match
    found in the normalized text maps back onto *text* with one lookup per bound.
    """
    chars: list[str] = []
    offsets: list[int] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\r" and i + 1 < n and text[i + 1] == "\n":
            chars.append("\n")
            offsets.append(i)
            i += 2
            continue
        chars.append(ch)
        offsets.append(i)
        i += 1
    return "".join(chars), offsets


def map_offset(text: str, offsets: list[int], normalized_index: int) -> int:
    """Translate a normalized-text index back to an index into *text*."""
    if normalized_index >= len(offsets):
        return len(text)
    return offsets[normalized_index]
