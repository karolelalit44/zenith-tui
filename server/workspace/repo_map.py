"""Repo map — generates directory structure and file summaries with tree-sitter symbol extraction.

Uses tree-sitter to parse source files, extract function/class definitions,
and rank files by relevance using a simplified PageRank-like algorithm.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Directories to always skip
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".cache", ".mypy_cache",
    ".pytest_cache", "coverage", ".nyc_output",
    ".tox", ".mypy", ".ruff_cache", "htmlcov",
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

# Extensions that tree-sitter can parse for symbol extraction
TREE_SITTER_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
}

# Tree-sitter query patterns for extracting definitions per language
# Format: (node_type, name_capture_group)
DEFINITION_QUERIES: dict[str, str] = {
    "python": """
(function_definition name: (identifier) @name) @def
(class_definition name: (identifier) @name) @def
""",
    "javascript": """
(function_declaration name: (identifier) @name) @def
(class_declaration name: (identifier) @name) @def
(lexical_declaration (variable_declarator name: (identifier) @name)) @def
""",
    "typescript": """
(function_signature name: (identifier) @name) @def
(class_declaration name: (type_identifier) @name) @def
(interface_declaration name: (type_identifier) @name) @def
(type_alias_declaration name: (type_identifier) @name) @def
(lexical_declaration (variable_declarator name: (identifier) @name)) @def
""",
    "go": """
(function_declaration name: (identifier) @name) @def
(type_declaration (type_spec name: (type_identifier) @name)) @def
""",
    "rust": """
(function_item name: (identifier) @name) @def
(struct_item name: (type_identifier) @name) @def
(enum_item name: (type_identifier) @name) @def
(impl_item name: (type_identifier) @name) @def
(trait_item name: (type_identifier) @name) @def
""",
    "java": [
        "(method_declaration name: (identifier) @name) @def",
        "(class_declaration name: (identifier) @name) @def",
        "(interface_declaration name: (identifier) @name) @def",
    ],
    "ruby": [
        "(method name: (identifier) @name) @def",
        "(class name: (constant) @name) @def",
        "(module name: (constant) @name) @def",
    ],
    "c": [
        "(function_declarator declarator: (identifier) @name) @def",
        "(type_definition (type_identifier) @name) @def",
        "(struct_specifier name: (type_identifier) @name) @def",
    ],
    "cpp": [
        "(function_declarator declarator: (identifier) @name) @def",
        "(class_specifier name: (type_identifier) @name) @def",
        "(struct_specifier name: (type_identifier) @name) @def",
    ],
}


class RepoMap:
    """Generates repository structure, file summaries, and symbol-based repo maps."""

    def __init__(self, workspace_root: str) -> None:
        self.root = Path(workspace_root).resolve()
        self._symbol_cache: dict[str, list[dict[str, Any]]] = {}
        self._language_cache: dict[str, Any] = {}

    def _get_language(self, lang_name: str) -> Any | None:
        """Get tree-sitter Language for a given language name."""
        if lang_name in self._language_cache:
            return self._language_cache[lang_name]

        try:
            from tree_sitter import Language as TSLanguage
            if lang_name == "python":
                from tree_sitter_python import language as py_lang
                lang_obj = TSLanguage(py_lang())
            elif lang_name == "javascript":
                from tree_sitter_javascript import language as js_lang
                lang_obj = TSLanguage(js_lang())
            elif lang_name == "typescript":
                from tree_sitter_typescript import language_typescript as ts_lang
                lang_obj = TSLanguage(ts_lang())
            elif lang_name == "typescript_tsx":
                from tree_sitter_typescript import language_tsx as tsx_lang
                lang_obj = TSLanguage(tsx_lang())
            elif lang_name == "go":
                from tree_sitter_go import language as go_lang
                lang_obj = TSLanguage(go_lang())
            elif lang_name == "rust":
                from tree_sitter_rust import language as rust_lang
                lang_obj = TSLanguage(rust_lang())
            elif lang_name == "java":
                from tree_sitter_java import language as java_lang
                lang_obj = TSLanguage(java_lang())
            elif lang_name == "ruby":
                from tree_sitter_ruby import language as ruby_lang
                lang_obj = TSLanguage(ruby_lang())
            elif lang_name in ("c", "cpp"):
                from tree_sitter_c import language as c_lang
                lang_obj = TSLanguage(c_lang())
            else:
                self._language_cache[lang_name] = None
                return None

            self._language_cache[lang_name] = lang_obj
            return lang_obj
        except ImportError:
            logger.debug("Tree-sitter language not available: %s", lang_name)
            self._language_cache[lang_name] = None
            return None

    def _extract_symbols(self, file_path: Path) -> list[dict[str, Any]]:
        """Extract function/class definitions from a source file using tree-sitter."""
        cache_key = str(file_path)
        if cache_key in self._symbol_cache:
            return self._symbol_cache[cache_key]

        ext = file_path.suffix.lower()
        lang_name = TREE_SITTER_EXTENSIONS.get(ext)
        if not lang_name:
            return []

        lang = self._get_language(lang_name)
        if lang is None:
            return []

        query_patterns = DEFINITION_QUERIES.get(lang_name)
        if not query_patterns:
            return []

        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
            source_bytes = source.encode("utf-8")

            from tree_sitter import Parser, Query, QueryCursor
            parser = Parser(lang)
            tree = parser.parse(source_bytes)

            # Combine query patterns (some languages return a list)
            if isinstance(query_patterns, list):
                query_scm = "\n".join(query_patterns)
            else:
                query_scm = query_patterns

            query = Query(lang, query_scm)

            # tree-sitter >= 0.25 removed Query.captures(); prefer QueryCursor
            captures: dict[str, list[Any]] = {}
            if hasattr(query, "captures"):
                captures = query.captures(tree.root_node)
            else:
                cursor = QueryCursor(query)
                for _pattern_index, groups in cursor.matches(tree.root_node):
                    for cap_name, nodes in groups.items():
                        captures.setdefault(cap_name, []).extend(nodes)

            symbols: list[dict[str, Any]] = []
            seen_names: set[str] = set()

            for capture_name, nodes in captures.items():
                if not (capture_name == "name" or capture_name.startswith("name.")):
                    continue
                kind = "def" if ".definition." in capture_name or capture_name == "name" else "ref"

                for node in nodes:
                    name = node.text.decode("utf-8", errors="replace")
                    if name in seen_names:
                        continue
                    seen_names.add(name)

                    # Find the parent node for line number
                    line = node.start_point[0]
                    symbols.append({
                        "name": name,
                        "kind": kind,
                        "line": line,
                    })

            self._symbol_cache[cache_key] = symbols
            return symbols

        except Exception as e:
            logger.debug("Failed to extract symbols from %s: %s", file_path, e)
            self._symbol_cache[cache_key] = []
            return []

    def _build_reference_graph(
        self, all_files: list[Path],
    ) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        """Build a reference graph: which files define and reference which names."""
        defines: dict[str, set[str]] = defaultdict(set)
        references: dict[str, set[str]] = defaultdict(set)

        for file_path in all_files:
            symbols = self._extract_symbols(file_path)
            rel = str(file_path.relative_to(self.root))
            for sym in symbols:
                if sym["kind"] == "def":
                    defines[sym["name"]].add(rel)
                else:
                    references[sym["name"]].add(rel)

        return dict(defines), dict(references)

    def _rank_files(
        self,
        all_files: list[Path],
        chat_files: list[str] | None = None,
    ) -> list[str]:
        """Rank files by relevance using a simplified PageRank-like algorithm.

        Files that define names referenced by many other files get higher ranks.
        Chat files (files the user is working on) get a boost.
        """
        if not all_files:
            return []

        defines, references = self._build_reference_graph(all_files)

        # Build file → relevance score
        file_scores: dict[str, float] = {}

        for file_path in all_files:
            rel = str(file_path.relative_to(self.root))
            score = 1.0  # Base score

            # Boost for files that define many names (high centrality)
            names_defined = {name for name, files in defines.items() if rel in files}
            score += len(names_defined) * 2.0

            # Boost for files whose defined names are referenced by many other files
            for name in names_defined:
                referencing_files = references.get(name, set())
                score += len(referencing_files) * 0.5

            # Boost for chat files (files the user is working on)
            if chat_files and rel in chat_files:
                score *= 3.0

            file_scores[rel] = score

        # Sort by score descending
        ranked = sorted(file_scores.items(), key=lambda x: -x[1])
        return [rel for rel, _ in ranked]

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
            for m in matches[:2]:
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

    def get_repo_map(
        self,
        chat_files: list[str] | None = None,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a ranked repo map with file structure and symbol summaries.

        Returns a formatted string with the directory tree and key file
        definitions, prioritized by relevance ranking.
        """
        parts: list[str] = []

        # 1. Directory structure
        structure = self.get_structure(max_depth=3)
        tree_str = self._format_tree(structure)
        if tree_str:
            parts.append(f"Directory Structure:\n{tree_str}")

        # 2. Key files
        key_files = self.get_key_files()
        if key_files:
            parts.append("Key Files:\n" + "\n".join(f"  {f}" for f in key_files))

        # 3. Language summary
        summary = self.get_summary()
        parts.append(summary)

        # 4. Symbol summaries for top-ranked files
        all_source_files = [
            f for f in self.root.rglob("*")
            if f.is_file()
            and f.suffix.lower() in TREE_SITTER_EXTENSIONS
            and not any(skip in f.parts for skip in SKIP_DIRS)
            and not f.name.startswith(".")
        ]

        if all_source_files:
            ranked = self._rank_files(all_source_files, chat_files)
            # Token-budgeted symbol packing (Aider-style): include the
            # highest-ranked files first, dropping lower-ranked files until
            # the estimated token budget is met. Rough estimate: 1 token ≈ 4 chars.
            budget_chars = max_tokens * 4
            used_chars = sum(len(p) + 2 for p in parts)
            symbol_lines: list[str] = []
            for rel_path in ranked[:50]:  # Top 50 files by relevance
                file_path = self.root / rel_path
                symbols = self._extract_symbols(file_path)
                defs = [s for s in symbols if s["kind"] == "def"]
                if defs:
                    def_names = [f"  {d['name']} (line {d['line']})" for d in defs[:10]]
                    block = f"\n{rel_path}:\n" + "\n".join(def_names)
                    if used_chars + len(block) > budget_chars:
                        break
                    symbol_lines.append(block)
                    used_chars += len(block)

            if symbol_lines:
                parts.append("Key Definitions:" + "".join(symbol_lines))

        result = "\n\n".join(parts)

        # Hard fallback: if still over budget, truncate to the char budget
        estimated_tokens = len(result) // 4
        if estimated_tokens > max_tokens:
            result = result[:max_tokens * 4] + "\n\n... (truncated, ~%d tokens estimated)" % estimated_tokens

        return result

    def _format_tree(self, node: dict[str, Any], prefix: str = "", is_last: bool = True) -> str:
        """Format a directory tree as a string."""
        lines: list[str] = []
        connector = "" if prefix == "" else ("└── " if is_last else "├── ")
        name = node["name"]
        if node["type"] == "directory":
            lines.append(f"{prefix}{connector}{name}/")
        else:
            lines.append(f"{prefix}{connector}{name}")

        children = node.get("children", [])
        for i, child in enumerate(children):
            child_prefix = prefix + ("" if prefix == "" else ("    " if is_last else "│   "))
            lines.append(self._format_tree(child, child_prefix, i == len(children) - 1))

        return "\n".join(lines)
