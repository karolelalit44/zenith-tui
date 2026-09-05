from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from server.providers.token_counter import TokenCounter
from server.workspace.ignore import get_matcher

logger = logging.getLogger(__name__)
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
DEFINITION_QUERIES: dict[str, str | list[str]] = {
    "python": " (function_definition name: (identifier) @name) @def (class_definition name: (identifier) @name) @def ",
    "javascript": " (function_declaration name: (identifier) @name) @def (class_declaration name: (identifier) @name) @def (lexical_declaration (variable_declarator name: (identifier) @name)) @def ",
    "typescript": " (function_signature name: (identifier) @name) @def (class_declaration name: (type_identifier) @name) @def (interface_declaration name: (type_identifier) @name) @def (type_alias_declaration name: (type_identifier) @name) @def (lexical_declaration (variable_declarator name: (identifier) @name)) @def ",
    "go": " (function_declaration name: (identifier) @name) @def (type_declaration (type_spec name: (type_identifier) @name)) @def ",
    "rust": " (function_item name: (identifier) @name) @def (struct_item name: (type_identifier) @name) @def (enum_item name: (type_identifier) @name) @def (impl_item name: (type_identifier) @name) @def (trait_item name: (type_identifier) @name) @def ",
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
    def __init__(
        self, workspace_root: str, refresh: str = "auto", map_mul_no_files: int = 2
    ) -> None:
        self.root = Path(workspace_root).resolve()
        self.refresh = refresh
        self.map_mul_no_files = map_mul_no_files
        self._symbol_cache: dict[str, dict[str, Any]] = {}
        self._language_cache: dict[str, Any] = {}
        self._file_cache: list[Path] | None = None
        self._token_counter = TokenCounter()
        self._matcher = get_matcher(workspace_root)

    def _get_git_files(self) -> list[str] | None:
        from server.workspace.git import GitOps

        self._matcher.refresh()
        git = GitOps(str(self.root))
        if not git.is_git_repo():
            return None
        files: set[str] = set()
        code, stdout, _ = git._run("ls-files")
        if code == 0:
            for line in stdout.splitlines():
                line = line.strip()
                if line:
                    files.add(line)
        code, stdout, _ = git._run("status", "--porcelain", "--untracked-files=all")
        if code == 0:
            for line in stdout.splitlines():
                line = line.rstrip("\n")
                if len(line) < 4 or line[:2] != "??":
                    continue
                rel = line[3:]
                if self._matcher.is_ignored(rel):
                    continue
                files.add(rel)
        result: list[str] = []
        for rel in files:
            candidate = (self.root / rel).resolve()
            try:
                candidate.relative_to(self.root)
            except ValueError:
                continue
            if candidate.is_file():
                result.append(candidate.relative_to(self.root).as_posix())
        return sorted(result)

    def _list_files(self) -> list[Path]:
        self._matcher.refresh()
        git_files = self._get_git_files()
        if git_files is not None:
            return [self.root / f for f in git_files]
        result: list[Path] = []
        for f in self.root.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(self.root)
            if self._matcher.is_ignored(rel):
                continue
            result.append(f)
        return result

    def _iter_files(self) -> list[Path]:
        if self._file_cache is None:
            self._file_cache = self._list_files()
        return self._file_cache

    def _snapshot(self) -> str:
        h = hashlib.md5()
        for f in self._list_files():
            try:
                st = f.stat()
            except OSError:
                continue
            try:
                rel = f.relative_to(self.root).as_posix()
            except ValueError:
                continue
            h.update(f"{rel}|{st.st_mtime_ns}|{st.st_size}".encode("utf-8", "replace"))
        if self.refresh == "auto":
            try:
                from server.workspace.git import GitOps

                git = GitOps(str(self.root))
                if git.is_git_repo():
                    code, out, _ = git._run("rev-parse", "HEAD")
                    if code == 0 and out.strip():
                        h.update(out.strip().encode("utf-8"))
            except Exception:
                pass
        return h.hexdigest()

    def _get_language(self, lang_name: str) -> Any | None:
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
                from tree_sitter_rust import language as rust_lang  # type: ignore[import-not-found]

                lang_obj = TSLanguage(rust_lang())
            elif lang_name == "java":
                from tree_sitter_java import language as java_lang

                lang_obj = TSLanguage(java_lang())
            elif lang_name == "ruby":
                from tree_sitter_ruby import language as ruby_lang  # type: ignore[import-not-found]

                lang_obj = TSLanguage(ruby_lang())
            elif lang_name in ("c", "cpp"):
                from tree_sitter_c import language as c_lang  # type: ignore[import-not-found]

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
        cache_key = str(file_path)
        try:
            mtime = file_path.stat().st_mtime_ns
        except OSError:
            mtime = 0
        cached = self._symbol_cache.get(cache_key)
        if cached is not None and cached.get("mtime") == mtime:
            return cached["symbols"]
        symbols: list[dict[str, Any]] = []
        ext = file_path.suffix.lower()
        lang_name = TREE_SITTER_EXTENSIONS.get(ext)
        if lang_name:
            lang = self._get_language(lang_name)
            query_patterns = DEFINITION_QUERIES.get(lang_name)
            if lang is not None and query_patterns:
                try:
                    source = file_path.read_text(encoding="utf-8", errors="replace")
                    source_bytes = source.encode("utf-8")
                    from tree_sitter import Parser, Query, QueryCursor

                    parser = Parser(lang)
                    tree = parser.parse(source_bytes)
                    if isinstance(query_patterns, list):
                        query_scm = "\n".join(query_patterns)
                    else:
                        query_scm = query_patterns
                    query = Query(lang, query_scm)
                    captures: dict[str, list[Any]] = {}
                    if hasattr(query, "captures"):
                        captures = query.captures(tree.root_node)
                    else:
                        cursor = QueryCursor(query)
                        for _pattern_index, groups in cursor.matches(tree.root_node):
                            for cap_name, nodes in groups.items():
                                captures.setdefault(cap_name, []).extend(nodes)
                    seen_names: set[str] = set()
                    for capture_name, nodes in captures.items():
                        if not (capture_name == "name" or capture_name.startswith("name.")):
                            continue
                        kind = (
                            "def"
                            if ".definition." in capture_name or capture_name == "name"
                            else "ref"
                        )
                        for node in nodes:
                            raw_text = node.text
                            if raw_text is None:
                                continue
                            name = raw_text.decode("utf-8", errors="replace")
                            if name in seen_names:
                                continue
                            seen_names.add(name)
                            symbols.append(
                                {"name": name, "kind": kind, "line": node.start_point[0]}
                            )
                except Exception as e:
                    logger.debug("Failed to extract symbols from %s: %s", file_path, e)
        self._symbol_cache[cache_key] = {"mtime": mtime, "symbols": symbols}
        return symbols

    def _build_reference_graph(
        self, all_files: list[Path]
    ) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        defines: dict[str, set[str]] = defaultdict(set)
        references: dict[str, set[str]] = defaultdict(set)
        for file_path in all_files:
            symbols = self._extract_symbols(file_path)
            rel = file_path.relative_to(self.root).as_posix()
            for sym in symbols:
                if sym["kind"] == "def":
                    defines[sym["name"]].add(rel)
                else:
                    references[sym["name"]].add(rel)
        return (dict(defines), dict(references))

    def _rank_files(self, all_files: list[Path], chat_files: list[str] | None = None) -> list[str]:
        if not all_files:
            return []
        defines, references = self._build_reference_graph(all_files)
        file_scores: dict[str, float] = {}
        for file_path in all_files:
            rel = file_path.relative_to(self.root).as_posix()
            score = 1.0
            names_defined = {name for name, files in defines.items() if rel in files}
            score += len(names_defined) * 2.0
            for name in names_defined:
                referencing_files = references.get(name, set())
                score += len(referencing_files) * 0.5
            if chat_files and rel in chat_files:
                score *= 3.0
            file_scores[rel] = score
        ranked = sorted(file_scores.items(), key=lambda x: -x[1])
        return [rel for rel, _ in ranked]

    def get_structure(self, max_depth: int = 3) -> dict[str, Any]:
        structure: dict[str, Any] = {"name": self.root.name, "type": "directory", "children": []}
        self._matcher.refresh()
        self._scan(self.root, structure["children"], 0, max_depth)
        return structure

    def _scan(self, path: Path, children: list[dict[str, Any]], depth: int, max_depth: int) -> None:
        if depth >= max_depth:
            return
        try:
            items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return
        for item in items:
            try:
                rel = item.relative_to(self.root)
            except ValueError:
                continue
            if item.is_dir():
                if self._matcher.is_ignored_dir(rel):
                    continue
            elif self._matcher.is_ignored(rel):
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
                try:
                    node["size"] = item.stat().st_size
                except OSError:
                    node["size"] = 0
            children.append(node)

    def get_summary(self) -> str:
        counts: dict[str, int] = {}
        total_files = 0
        for f in self._iter_files():
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
        key_names = {
            "package.json",
            "pyproject.toml",
            "Cargo.toml",
            "go.mod",
            "Makefile",
            "Dockerfile",
            "docker-compose.yml",
            ".gitignore",
            ".env.example",
            "README.md",
            "tsconfig.json",
            "setup.py",
            "setup.cfg",
        }
        found = []
        for f in self._iter_files():
            if f.name in key_names:
                try:
                    found.append(f.relative_to(self.root).as_posix())
                except ValueError:
                    pass
            if len(found) >= 20:
                break
        return sorted(found)


    def _count_tokens(self, text: str) -> int:
        return self._token_counter.count(text, "cl100k_base")

    def _build_symbol_blocks(
        self, ranked_files: list[str], max_files: int
    ) -> list[tuple[str, str]]:
        blocks: list[tuple[str, str]] = []
        for rel_path in ranked_files[:max_files]:
            file_path = self.root / rel_path
            symbols = self._extract_symbols(file_path)
            defs = [s for s in symbols if s["kind"] == "def"]
            if defs:
                def_names = []
                for d in defs[:10]:
                    name = d["name"]
                    if len(name) > 100:
                        name = name[:97] + "..."
                    def_names.append(f"  {name} (line {d['line']})")
                blocks.append((rel_path, "\n" + rel_path + ":\n" + "\n".join(def_names)))
        return blocks

    def _fit_blocks_to_budget(
        self, blocks: list[tuple[str, str]], base_text: str, max_tokens: int
    ) -> list[tuple[str, str]]:
        header = "Key Definitions:"
        lo, hi = (0, len(blocks))
        best = 0
        while lo <= hi:
            mid = (lo + hi) // 2
            symbols_text = "".join(b[1] for b in blocks[:mid])
            total = self._count_tokens(base_text + "\n\n" + header + symbols_text)
            if total <= max_tokens:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return blocks[:best]


    def _format_tree(self, node: dict[str, Any], prefix: str = "", is_last: bool = True) -> str:
        lines: list[str] = []
        connector = "" if prefix == "" else "└── " if is_last else "├── "
        name = node["name"]
        if node["type"] == "directory":
            lines.append(f"{prefix}{connector}{name}/")
        else:
            lines.append(f"{prefix}{connector}{name}")
        children = node.get("children", [])
        for i, child in enumerate(children):
            child_prefix = prefix + ("" if prefix == "" else "    " if is_last else "│   ")
            lines.append(self._format_tree(child, child_prefix, i == len(children) - 1))
        return "\n".join(lines)

    def get_file_count(self) -> int:
        return len(self._iter_files())

    def get_repo_map(
        self,
        max_tokens: int = 1024,
        chat_files: list[str] | None = None,
        force_refresh: bool = False,
    ) -> str:
        if force_refresh:
            self._file_cache = None
            self._symbol_cache.clear()

        all_files = self._iter_files()
        if not all_files:
            return ""

        structure = self.get_structure()
        tree_text = self._format_tree(structure)
        base_text = f"Directory Structure:\n{tree_text}"

        if self._count_tokens(base_text) > max_tokens:
            lines = base_text.splitlines()
            while lines and self._count_tokens("\n".join(lines)) > max_tokens:
                lines.pop()
            return "\n".join(lines)

        ranked_files = self._rank_files(all_files, chat_files)
        blocks = self._build_symbol_blocks(ranked_files, max_files=len(ranked_files))
        fitted = self._fit_blocks_to_budget(blocks, base_text, max_tokens)
        if fitted:
            symbols_text = "".join(b[1] for b in fitted)
            return f"{base_text}\n\nKey Definitions:{symbols_text}"
        return base_text

