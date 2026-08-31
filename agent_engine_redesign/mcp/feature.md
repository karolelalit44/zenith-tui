# MCP (Model Context Protocol)

## Overview

How zenith connects to and exposes MCP servers and their tools to the model.

### How opencode does it

- Full **MCP SDK** client supporting **streamable HTTP, SSE, and stdio** transports (`mcp/index.ts`).
- **OAuth** support for HTTP providers (`mcp/auth.ts`, `oauth-provider.ts`, `oauth-callback.ts`) â€” pending/callback flow.
- **Catalog** (`mcp/catalog.ts`): paginated `tools/list` (`MAX_LIST_PAGES=1000`, `DEFAULT_TIMEOUT=30000`), tolerant `outputSchema` handling, plus `tools/prompts`, `resources`, `resourceTemplates`.
- Tool naming `sanitize(client)_name`.

### How codex does it

- Plugin-based MCP catalog (`ResolvedMcpCatalog`), `McpToolCatalogCache`, split `McpToolCall`/`McpToolExposure` (`mcp_tool_call/`, `mcp_tool_exposure.rs`).
- Config-driven server registration with optional-server timeout while building the catalog; logging + tool visibility.

### What zenith has today

- `server/mcp/client.py` (156): custom **stdio-only** client, raw JSON-RPC, manual Content-Length framing (`_encode_message`), protocol `2024-11-05`, request-id futures, `_read_loop` with `readexactly(content_length)`.
- `server/mcp/manager.py` (74): start/stop, `build_wrappers()` â†’ `McpToolWrapper` per discovered tool.
- `server/toolkit/tools/mcp_tool.py` (60): the `mcp_<server>_<tool>` tool (matches opencode naming).
- `config/settings.py`: `McpServerConfig` (command/args/env) loaded from `ZENITH_MCP_SERVERS` env JSON.

### What is correct

- Hand-rolled framed stdio transport is standards-correct and adequate for local stdio servers; protocol `2024-11-05` is current. `mcp_<server>_<tool>` naming matches references.

### What is wrong / over-engineered / incorrect / missing

**Over-engineered:**
- Reimplementing the MCP wire protocol/pending-request machinery by hand duplicates an MCP SDK (`@modelcontextprotocol/sdk` or the official Python `mcp` package). Every timeout/reframe edge case (`_read_loop` header parsing, `readexactly` blocking) is what an SDK solves.

**Missing:**
- **No non-stdio transports** (streamable HTTP / SSE) â€” opencode supports all three.
- **No OAuth** for HTTP providers.
- No `tools/prompts` / `resources` / list pagination (`McpCatalog.paginate`) â€” zenith does a single non-paginated `tools/list`.
- No tolerant `outputSchema` fallback for bad server `$ref`.

## What we will do

- Adopt an MCP SDK rather than hand-rolling the wire protocol, if the protocol surface grows.
- Support stdio (primary) and add streamable-HTTP/SSE + OAuth where providers require it.
- Use paginated catalog discovery with tolerant outputSchema, listing tools/prompts/resources.

## What we will REMOVE
- Hand-rolled JSON-RPC framing / request pending table in `mcp/client.py` (replace with SDK).

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| (none specific here) | â€” | â€” |

## Verification / signoff
- [ ] MCP SDK-based client (stdio + optional HTTP/SSE + OAuth)
- [ ] Paginated catalog discovery, tolerant outputSchema
- [ ] tools/prompts/resources surfaced where available
- [ ] `mcp_<server>_<tool>` naming kept
- [ ] ruff + pytest + runtime smoke pass

## Status: Pending
