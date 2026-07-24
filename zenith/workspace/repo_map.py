"""Repo map — generates directory structure and file summaries."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Directories to always skip
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".cache", ".mypy_cache",
    ".pytest_cache", "coverage", ".nyc_output",
}

# File extensions to count by language
LANGUAGE_MAP = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".rb": "Ruby",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".css": "CSS",
    ".html": "HTML",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".md": "Markdown",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
}


class RepoMap:
    """Generates repository structure and summary statistics."""

    def __init__(self, workspace_root: str) -> None:
        self.root = Path(workspace_root).resolve()

    def get_structure(self, max_depth: int = 3) -> dict[str, Any]:
        """Get directory tree structure up to max_depth."""
        structure: dict[str, Any] = {
            "name": self.root.name,
            "type": "directory",
            "children": [],
        }
        self._scan(self.root, structure["children"], 0, max_depth)
        return structure

    def _scan(
        self,
        path: Path,
        children: list[dict[str, Any]],
        depth: int,
        max_depth: int,
    ) -> None:
        if depth >= max_depth:
            return

        try:
            items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return

        for item in items:
            if item.name in SKIP_DIRS or item.name.startswith("."):
                continue
            if item.name == "node_modules" or item.name == "__pycache__":
                continue

            node: dict[str, Any] = {
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
            }

            if item.is_dir():
                node["children"] = []
                self._scan(item, node["children"], depth + 1, max_depth)
                # Only skip truly empty dirs (not truncated by max_depth)
                if not node["children"] and depth + 1 < max_depth:
                    continue
            else:
                node["size"] = item.stat().st_size

            children.append(node)

    def get_summary(self) -> str:
        """Get file count summary by language."""
        counts: dict[str, int] = {}
        total_files = 0

        for f in self.root.rglob("*"):
            if not f.is_file():
                continue
            if any(skip in f.parts for skip in SKIP_DIRS):
                continue
            if f.name.startswith("."):
                continue

            total_files += 1
            ext = f.suffix.lower()
            lang = LANGUAGE_MAP.get(ext, ext.lstrip(".") or "other")
            counts[lang] = counts.get(lang, 0) + 1

        if not counts:
            return "Empty repository."

        sorted_counts = sorted(counts.items(), key=lambda x: -x[1])
        parts = [f"{lang}: {count}" for lang, count in sorted_counts[:10]]
        return f"Total: {total_files} files. Top languages: {', '.join(parts)}"

    def get_key_files(self) -> list[str]:
        """Find important files (config, entry points, etc.)."""
        key_names = {
            "package.json", "pyproject.toml", "Cargo.toml", "go.mod",
            "Makefile", "Dockerfile", "docker-compose.yml",
            ".gitignore", ".env.example", "README.md",
            "tsconfig.json", "setup.py", "setup.cfg",
        }

        found = []
        for name in key_names:
            matches = list(self.root.rglob(name))
            for m in matches[:2]:  # limit per name
                try:
                    found.append(str(m.relative_to(self.root)))
                except ValueError:
                    pass

        return sorted(found)[:20]

    def get_file_count(self) -> int:
        """Count total files in repo."""
        count = 0
        for f in self.root.rglob("*"):
            if not f.is_file():
                continue
            if any(skip in f.parts for skip in SKIP_DIRS):
                continue
            if f.name.startswith("."):
                continue
            count += 1
        return count
