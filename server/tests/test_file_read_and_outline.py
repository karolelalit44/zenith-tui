from __future__ import annotations

from pathlib import Path

import pytest

from server.config.constants import DEFAULT_FILE_READ_LINES
from server.toolkit.tools.file_read import FileReadTool


class TestFileReadAndOutline:
    @pytest.mark.asyncio
    async def test_file_read_default_limit_250_lines(self, temp_dir: Path):
        file_path = temp_dir / "large.py"
        lines = [f"# line {i}" for i in range(1, 501)]
        file_path.write_text("\n".join(lines))

        tool = FileReadTool()
        result = await tool.execute({"path": "large.py"}, str(temp_dir))
        assert result.success
        assert result.metadata["showing"] == DEFAULT_FILE_READ_LINES
        assert result.metadata["total_lines"] == 500
        assert result.metadata["truncated"] is True
        assert f"Showing lines 1-{DEFAULT_FILE_READ_LINES} of 500 total lines" in result.output
        assert f"pass offset={DEFAULT_FILE_READ_LINES}" in result.output

    @pytest.mark.asyncio
    async def test_file_read_pagination_with_offset(self, temp_dir: Path):
        file_path = temp_dir / "paginated.py"
        lines = [f"val_{i} = {i}" for i in range(1, 301)]
        file_path.write_text("\n".join(lines))

        tool = FileReadTool()
        result = await tool.execute(
            {"path": "paginated.py", "offset": 100, "limit": 50}, str(temp_dir)
        )
        assert result.success
        assert result.metadata["showing"] == 50
        assert result.metadata["offset"] == 100
        assert "101: val_101 = 101" in result.output
        assert "150: val_150 = 150" in result.output
        assert "151:" not in result.output

    @pytest.mark.asyncio
    async def test_file_read_outline_python(self, temp_dir: Path):
        code = """import os

class DatabaseManager:
    def __init__(self):
        pass

    async def connect(self):
        pass

def global_helper():
    pass
"""
        (temp_dir / "db.py").write_text(code)
        tool = FileReadTool()
        result = await tool.execute({"path": "db.py", "outline": True}, str(temp_dir))
        assert result.success
        assert result.metadata.get("outline") is True
        assert "Symbol outline for db.py" in result.output
        assert "class DatabaseManager" in result.output
        assert "def __init__" in result.output
        assert "async def connect" in result.output
        assert "def global_helper" in result.output

    @pytest.mark.asyncio
    async def test_file_read_outline_markdown(self, temp_dir: Path):
        doc = """# Main Header

Some intro text

## Section 1: Overview
Content

### Subsection 1.1
Details
"""
        (temp_dir / "doc.md").write_text(doc)
        tool = FileReadTool()
        result = await tool.execute({"path": "doc.md", "outline": True}, str(temp_dir))
        assert result.success
        assert "# Main Header" in result.output
        assert "## Section 1: Overview" in result.output
        assert "### Subsection 1.1" in result.output
