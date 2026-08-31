# Tool Guidelines

Read this file only when a tool's schema is insufficient: what it expects, what it returns, how to use it correctly. For general queries and simple reads, the schema suffices.

## Compact model rules

CRITICAL INSTRUCTIONS FOR COMPACT MODELS:
1. NEVER output chat preambles. Emit tool calls or a concise answer (<4 lines).
2. Avoid redundant identical tool calls; retry only when there is a reason, such as a
   transient failure, and alter the approach when appropriate.
3. Do not repeat a tool action without a reason; re-reading or re-editing is allowed
   only when repository state changed or a previous operation failed and correction is required.
4. When the task is complete, output your final summary text and stop issuing tools.
5. A tool call that already succeeded this turn will be skipped.

## General rules

- Scope every glob to a subdirectory; never `**/*` from the repo root (it matches
  node_modules and .git and floods context).
- Inspect a folder before writing into it; never overwrite or duplicate work.
- Refine files with file_read then file_edit; never blindly overwrite.
- Batch independent tool calls; never dependent ones.
- Generated projects: install deps, run tests.
- For external/current facts, retrieve authoritative evidence as needed and verify claims against the retrieved source.
- Unrunnable verification (no network, missing runtime): say so. Never claim success.
- General queries: answer in markdown. No tools.

## Tool reference

### file_read
- Purpose: read a file or a slice from the workspace.
- Input: `path` (required), `offset` (0-indexed start line), `limit` (max lines).
- Output: numbered lines `N: content`; metadata includes `total_lines`/`showing`.
- Guidelines: read small slices, not whole files; use offset/limit to page through
  large files. Path must stay inside the workspace.

### file_edit
- Purpose: change an existing file via exact search-and-replace.
- Input: `path`, `old_content` (exact text to replace), `new_content`.
- Output: confirmation of the applied edit.
- Guidelines: read the file first so `old_content` matches exactly.

### file_write
- Purpose: create a new file or overwrite an existing one.
- Input: `path`, `content` (full file body), `overwrite` (bool, default false).
- Output: `Created <path> (<bytes> bytes)`.
- Guidelines: missing parent directories are created automatically - do not run
  mkdir first. No placeholders; write the full intended content once. Replace an
  existing file only with `overwrite: true`; otherwise prefer file_edit. In plan
  mode, writing is restricted to plan.md/todo.md.

### bash
- Purpose: run a command in the workspace (tests, builds, installs, git).
- Input: `command`, `timeout`, `run_in_background`, `auto_background_after`.
- Output: stdout + exit code; long output is head/tail-trimmed with a marker.
- Guidelines: use PowerShell syntax on Windows, bash on Unix (see the env section).
  Use it only when no dedicated tool fits. Long commands run in a background job;
  poll with job_output / terminate with job_kill.

### glob
- Purpose: find files by glob pattern.
- Input: `pattern` (required, e.g. 'app/**/*.py'), `path`.
- Output: matched paths, capped at 500 results.
- Guidelines: always scope the pattern to a subdirectory; never `**/*` from the root.

### grep
- Purpose: search file contents by regex.
- Input: `pattern` (required), `path`, `include` (file filter).
- Output: `path:line: content` matches, or "No matches found".
- Guidelines: scope `path` so results stay small.

### discover_capabilities
- Purpose: list every capability and the tools that provide it.
- Input: none.
- Output: capability list with read-only/mutating flags and tool names.

### get_tool_definition
- Purpose: load the full schema + metadata for a tool not in the always-on set.
- Input: `tool_name` (required).
- Output: JSON with the tool's function schema and metadata.
- Guidelines: load a tool definition only when needed; loaded tools persist for the
  session. Never load a tool you already have.
