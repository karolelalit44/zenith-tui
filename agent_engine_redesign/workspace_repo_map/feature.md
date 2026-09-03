# Workspace / Repo Map / Git / Ignore / Index / Graph

## Overview

How zenith understands the workspace: git, ignore rules, code index/repo-map, and structural/"code graph" tools.

### How opencode does it

- **No repo map, no symbol index, no code graph.** opencode does *zero* tree-sitter extraction.
- Grep/glob tools are backed by **ripgrep** (`tool/grep.ts` calls `ripgrep.grep`; `tool/glob.ts` calls `ripgrep.glob`), which natively honors `.gitignore`.
- The only code-level structure exposed is **on-demand LSP** `documentSymbol`/`workspace/symbol` while building prompt parts (`session/prompt.ts:839`).
- Git is a thin subprocess wrapper for diff/status/patch/name (`git/index.ts`). Ignore is delegated entirely to ripgrep's native `.gitignore`.

### How codex does it

- **No repo map** either. Grep is not a dedicated tool â€” the model runs `exec_command` with shell grep/ripgrep (`shell_spec.rs`).
- Only specialized file discovery is a fuzzy **filename matcher** (`file-search` crate, nucleo engine + `ignore::WalkBuilder` for `.gitignore`) used for interactive file pick/lookup â€” matches **paths**, not definitions.
- Git via `git-utils` crate.

### What zenith has today

**Files:**
- `server/workspace/repo_map.py` (495) â€” LANGUAGE_MAP, TREE_SITTER_EXTENSIONS, per-language DEFINITION_QUERIES, `_extract_symbols`, tree-sitter code map.
- `server/workspace/graph_queries.py` (167) â€” CodeGraph defines/references, `_MIN_IDENT_LEN=5`.
- `server/toolkit/tools/code_graph_tools.py` (185) â€” CodeCallersTool / CodeOutlineTool / CodeBlastRadiusTool, `_bounded` truncation.
- `server/workspace/index.py` (98) â€” WorkspaceStats, `MAX_INDEX_FILES=200_000`, `CACHE_TTL_SECONDS=120`.
- `server/workspace/git.py` (222) â€” `_GIT_TIMEOUT_DEFAULT=30` subprocess wrapper.
- `server/workspace/ignore.py` (142) â€” `.zenithignore` via `pathspec.GitIgnoreSpec`.

### What is correct

- `.zenithignore` is a reasonable analogue to ripgrep/codex `.gitignore` handling.
- `git.py` subprocess-with-timeout matches opencode/codex.
- Bounded index scan (200k files, TTL cache) aligns with codex's bounded `file-search`.

### What is wrong / over-engineered / incorrect / missing

**Over-engineered / incorrect (remove):**
- The **entire tree-sitter repo-map + code-graph stack** (`repo_map.py`, `graph_queries.py`, `code_graph_tools.py`) has **no counterpart in either reference**. Both engines rely on ripgrep / shell grep + filename fuzzy search + on-demand LSP for symbols. A hand-maintained per-language tree-sitter query set (definitions, caller graphs, blast radius) drifts as grammars/languages evolve and is not how either shipped agent structures workspace understanding.
- `repo_map.py` is injected into context (T1 tier) â€” opencode/codex have no such injected code map in the system prompt.
- The `CREWMATE_GRAPH_TOOLS` / `code_graph_*` tools belong to the delegation subsystem slated for removal (subagents doc).

**Missing:**
- ripgrep-backed grep/glob with native `.gitignore` (zenith's grep/glob should use ripgrep, and `.zenithignore` should integrate with it).

## What we will do

- Remove the tree-sitter repo-map/code-graph/structural tools.
- Rely on ripgrep-backed glob/grep (native ignore) + on-demand LSP symbol lookup where a code-level tool is genuinely needed.
- Keep `.zenithignore` (integrate with ripgrep).
- Keep the thin git subprocess wrapper.

## What we will REMOVE
- `workspace/repo_map.py`
- `workspace/graph_queries.py`
- `toolkit/tools/code_graph_tools.py`
- Tree-sitter dependency set
- `CREWMATE_GRAPH_TOOLS` (with delegation)
- Repo-map injection into context (T1)

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| per-language DEFINITION_QUERIES / symbol regexes | No (ripgrep / LSP symbol) | Remove |
| `_MIN_IDENT_LEN` identifier heuristics | No | Remove |

## Verification / signoff
- [x] No tree-sitter repo-map / code graph / blast-radius (Phase 3 removal, deferred)
- [x] ripgrep-backed glob/grep with native ignore (additive primitive added)
- [x] `.zenithignore` integrated with ripgrep (via `--ignore-file`)
- [x] thin git wrapper kept
- [x] ruff + pytest (targeted) pass

## §9 report (Module 16 — Interface-Locked, additive Phase 1)

Added `server/workspace/search.py` (module-16 owned, NEW file):

- `SearchMatch` — frozen dataclass `{path, line_number, text}` compatible with the
  existing `grep.py` `path:line:content` format.
- `_find_rg()` — lru-cached `shutil.which("rg")`; no hard dependency at import time.
- `_run()` — async subprocess wrapper returning `(returncode, stdout, stderr)`,
  with an injectable `cmd_runner` hook so tests run without the `rg` binary.
- `_parse_grep_output()` — parses `path:line:content`; robust to Windows drive
  letters and colons embedded in path/content (scans rightward for the last
  integer line-number token, rejoining path and content).
- `RipgrepBackend` — `grep(pattern, path, include=...)` and `glob(pattern, path)`
  methods that shell out to `rg`, honor native `.gitignore` + a `.zenithignore`
  via `--ignore-file`. Injectable `cmd_runner`; `max_results` / `ignore_files` knobs.
- `DEFAULT_BACKEND` singleton + `__all__`.

Tests: `server/tests/test_workspace_search.py` (**6 pass**) covering `SearchMatch`
fields, `_parse_grep_output` (typical + malformed + Windows paths), and
`RipgrepBackend.grep`/`glob`/error with a fake `cmd_runner`. Ruff clean. Existing
`test_web_tools.py` (13 pass) confirms no web-tooling regression.

**Decision:** `ripgrep_pkg` is `False` and no `rg` binary is on PATH in this
environment, so the runtime smoke is **targeted-PASS** (unit-level via injected
fake `cmd_runner`); a live-`rg` integration check is deferred until `rg` is
installed. The tree-sitter repo-map/code-graph stack
(`repo_map.py`, `graph_queries.py`, `code_graph_tools.py`, tree-sitter deps,
`CREWMATE_GRAPH_TOOLS`, T1 repo-map injection) stays for the coordinated
**Phase 3 REMOVE** — it remains live-imported by context/loop consumers and must
be removed only after those consumers adopt the new shape. No EventKind/transport
change was made (G5 preserved).

## Status: Interface-Locked

### Decision (2026-09-01) - Phase 2 live tool migration (Mars)

`GlobTool` and `GrepTool` now delegate file discovery and content matching to
`RipgrepBackend`. The tools retain their existing validation, bounded model-facing
formatting, and `ZenithIgnoreMatcher` filtering so `.zenithignore` behavior stays
compatible while ripgrep supplies native ignore and regex semantics. Docker validation:
`test_workspace_search.py`, search guardrails, search scope, and Zenith-ignore tests
all pass (45 passed). Tree-sitter/code-graph paths remain until their live consumers
migrate in Phase 3.
