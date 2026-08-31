# LSP (Language Server Protocol)

## Overview

How zenith uses language servers for symbols, diagnostics, and rename.

### How opencode does it

- Mature LSP (`lsp/lsp.ts`, `client.ts`, `server.ts`, `language.ts`, `diagnostic.ts`):
  - **150ms diagnostics debounce**, 45s init timeout, 5s doc / 10s full-doc wait, 3s request timeout (`client.ts`).
  - **Incremental sync** (`TEXT_DOCUMENT_SYNC_INCREMENTAL=2`) with version tracking, document-open caching, `didChange` full-range replacement.
  - **Pull + push diagnostics** merged/deduped; capability registration (`client/registerCapability`, `workspace/configuration`, `workspaceFolders`).
  - Per-server launch config with `NearestRoot` discovery and runtime auto-install.
  - `LANGUAGE_EXTENSIONS` map.

### How codex does it

- **None.** No LSP implementation in codex. No definition/diagnostics/rename tooling from an LSP.

### What zenith has today

- `server/lsp/client.py` (392): `DEFAULT_SERVERS` map (pyright, typescript-language-server, gopls, rust-analyzer, jdtls, solargraph, clangd), `_EXT_TO_LANG_ID` map, framed JSON-RPC client reuse.
- `server/lsp/manager.py` (85): `_build_ext_index`, `get_server_for_file`, lazy `get_client` via `shutil.which`.
- Tools: `lsp_definition.py`, `lsp_diagnostics.py`, `lsp_rename.py`.
- **Full-file open/close per call**: each request `did_open` â€¦ operate â€¦ `did_close` (`client.py:200-309`), no persistent document, no versioning. Diagnostics call does `asyncio.sleep(0.5)` after open waiting for a push.

### What is correct

- The server map and language-id map are reasonable (match opencode intent). Feature set (definition/diagnostics/rename) is genuinely useful and exceeds codex.

### What is wrong / over-engineered / incorrect / missing

**Wrong (performance/design):**
- **open-close-per-request** against live servers is naive â€” each call re-`didOpen`, sleeps, then closes. The fixed 0.5s sleep polling a notification queue once is a **race** (opencode waits for the specific document's publish or pulls via capability). Non-deterministic results.
- Reimplements LSP JSON-RPC framing (third such rewrite after MCP) â€” same SDK argument (`vscode-jsonrpc` / `pygls`).

**Missing:**
- Persistent document set with versioning across requests
- Incremental sync
- Pull+push diagnostic merge and capability registration
- Debounce, workspace-folder / `workspace/configuration` negotiation
- Nearest-root discovery + runtime install (zenith uses only `shutil.which`)

## What we will do

- Keep documents open, keyed by version, across requests (mirror opencode `client.ts`).
- Wait for the specific document's publish / use pull diagnostics instead of a fixed sleep.
- Support incremental sync and diagnostic merge.
- Use an LSP SDK/rpc library rather than hand-rolled framing.

## What we will REMOVE
- The open-close-per-call pattern
- The fixed 0.5s `asyncio.sleep` diagnostic race
- Hand-rolled LSP JSON-RPC framing (use a library)

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| (none specific here) | â€” | â€” |

## Verification / signoff
- [ ] Persistent documents with versioning
- [ ] Deterministic diagnostics (targeted publish / pull), no fixed sleep
- [ ] Incremental sync + diagnostic merge
- [ ] LSP SDK/rpc library, not hand-rolled framing
- [ ] ruff + pytest + runtime smoke pass

## Status: Pending
