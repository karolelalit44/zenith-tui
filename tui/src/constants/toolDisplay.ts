import { formatDuration } from '../utils/text';

export const FILE_WRITE_TOOL = 'file_write';
export const FILE_EDIT_TOOL = 'file_edit';
export const MULTI_EDIT_TOOL = 'multi_edit';
export const FILE_DELETE_TOOL = 'file_delete';
export const FILE_READ_TOOL = 'file_read';
export const LIST_DIR_TOOL = 'list_dir';
export const BASH_TOOL = 'bash';
export const EXECUTE_TOOL = 'execute';
export const RUN_COMMAND_TOOL = 'run_command';
export const TERMINAL_TOOL = 'terminal';
export const GET_TOOL_DEFINITION_TOOL = 'get_tool_definition';
export const DISCOVER_CAPABILITIES_TOOL = 'discover_capabilities';
export const WEBSEARCH_TOOL = 'websearch';
export const WEBFETCH_TOOL = 'webfetch';
export const BACKGROUND_TOOL = 'background';
export const JOB_OUTPUT_TOOL = 'job_output';
export const JOB_KILL_TOOL = 'job_kill';
export const LSP_DEFINITION_TOOL = 'lsp_definition';
export const LSP_DIAGNOSTICS_TOOL = 'lsp_diagnostics';
export const LSP_RENAME_TOOL = 'lsp_rename';
export const AGENT_TOOL = 'agent';
export const AGENT_TOOL_ALIAS = 'agent_tool';
export const TODO_TOOL = 'todo';
export const MCP_TOOL = 'mcp_tool';

export const TOOL_VERB_LABELS: Record<string, string> = {
  [FILE_WRITE_TOOL]: 'Create',
  create_file: 'Create',
  write_file: 'Create',
  [FILE_EDIT_TOOL]: 'Update',
  [MULTI_EDIT_TOOL]: 'Update',
  edit_file: 'Update',
  [FILE_DELETE_TOOL]: 'Delete',
  delete_file: 'Delete',
  [FILE_READ_TOOL]: 'Read',
  read_file: 'Read',
  [LIST_DIR_TOOL]: 'List',
  glob: 'Glob',
  grep: 'Grep',
  grep_search: 'Grep',
  [WEBSEARCH_TOOL]: 'Search',
  [WEBFETCH_TOOL]: 'Fetch',
  [BASH_TOOL]: 'Run',
  [EXECUTE_TOOL]: 'Run',
  [RUN_COMMAND_TOOL]: 'Run',
  [TERMINAL_TOOL]: 'Run',
  [BACKGROUND_TOOL]: 'Launch',
  [JOB_OUTPUT_TOOL]: 'Inspect',
  [JOB_KILL_TOOL]: 'Kill',
  [GET_TOOL_DEFINITION_TOOL]: 'Load',
  [DISCOVER_CAPABILITIES_TOOL]: 'Discover',
  [LSP_DEFINITION_TOOL]: 'Inspect',
  [LSP_DIAGNOSTICS_TOOL]: 'Diagnose',
  [LSP_RENAME_TOOL]: 'Rename',
  [AGENT_TOOL]: 'Delegate',
  [AGENT_TOOL_ALIAS]: 'Delegate',
  [TODO_TOOL]: 'Track',
  mcp_tool: 'MCP action',
};

export function getToolVerbLabel(tool: string): string {
  return TOOL_VERB_LABELS[tool] || tool;
}

export const TOOL_STEP_SKIP_PARAMS = new Set([
  'content',
  'file_content',
  'old_content',
  'new_content',
  'data',
  'file_data',
  'filetext',
  'file_text',
  'source',
  'text',
  'body',
  'input',
  'output',
]);

export const TOOL_STEP_PRIMARY_KEYS = [
  'path',
  'filepath',
  'command',
  'url',
  'query',
  'pattern',
  'glob',
  'job_id',
  'new_name',
  'task_id',
  'symbol',
] as const;

export function getToolStepPrimaryParam(
  _tool: string,
  params: Record<string, unknown>,
): { key: string; value: string } | null {
  for (const key of TOOL_STEP_PRIMARY_KEYS) {
    if (params[key] !== undefined && params[key] !== null) {
      return { key, value: String(params[key]) };
    }
  }
  return null;
}

/** Parse an MCP wrapper tool name (`mcp_<server>_<tool>`) into its parts. */
export function parseMcpToolName(tool: string): { server: string; action: string } | null {
  const parts = tool.split('_');
  if (parts.length < 2 || parts[0] !== 'mcp') return null;
  const server = parts[1] || '';
  const action = parts.slice(2).join('_') || '';
  return { server, action };
}

/** Count errors and warnings from an lsp_diagnostics metadata payload. */
export function countLspDiagnostics(metadata: Record<string, unknown>): {
  errors: number;
  warnings: number;
} {
  const diagnostics = Array.isArray(metadata.diagnostics) ? metadata.diagnostics : [];
  let errors = 0;
  let warnings = 0;
  for (const d of diagnostics) {
    const severity = String((d as Record<string, unknown>)?.severity ?? '').toLowerCase();
    if (severity === 'error' || severity === '1') errors++;
    else if (severity === 'warning' || severity === '2') warnings++;
  }
  return { errors, warnings };
}

function linesFrom(metadata: Record<string, unknown>): number | undefined {
  const total = metadata.total_lines;
  return typeof total === 'number' ? total : undefined;
}

function jobIdFrom(metadata: Record<string, unknown>): string {
  const id = metadata.job_id;
  return id !== undefined && id !== null ? String(id) : '';
}

interface StatusSource {
  metadata: Record<string, unknown>;
  params?: Record<string, unknown>;
}

function pathFrom(source: StatusSource): string {
  const { metadata, params } = source;
  return (
    String(metadata.path || '') ||
    String(params?.filepath || '') ||
    String(params?.path || '')
  );
}

function formatFileWriteStatus(source: StatusSource): string {
  const path = pathFrom(source);
  const size = typeof source.metadata.size === 'number' ? `${source.metadata.size} B` : '';
  return `● Create${path ? ` ${path}` : ''}${size ? ` (${size})` : ''}`;
}

function formatFileEditStatus(source: StatusSource): string {
  const path = pathFrom(source);
  return `● Update${path ? ` ${path}` : ''}`;
}

function formatFileDeleteStatus(source: StatusSource): string {
  const path = pathFrom(source);
  return `✗ Delete${path ? ` ${path}` : ''} (removed from workspace)`;
}

function formatFileReadStatus(source: StatusSource): string {
  const path = pathFrom(source);
  const lines = linesFrom(source.metadata);
  return `✓ Read${path ? ` ${path}` : ''}${lines !== undefined ? ` (${lines} lines)` : ''}`;
}

function formatListDirStatus(source: StatusSource): string {
  const path = pathFrom(source);
  const subdirs = typeof source.metadata.subdirs === 'number' ? source.metadata.subdirs : undefined;
  const files = typeof source.metadata.files === 'number' ? source.metadata.files : undefined;
  const parts: string[] = [];
  if (subdirs !== undefined) parts.push(`${subdirs} subdir${subdirs === 1 ? '' : 's'}`);
  if (files !== undefined) parts.push(`${files} file${files === 1 ? '' : 's'}`);
  return `✓ List${path ? ` ${path}` : ''}${parts.length > 0 ? ` (${parts.join(', ')})` : ''}`;
}

function formatGlobStatus(source: StatusSource): string {
  const pattern = String(source.metadata.pattern || source.params?.pattern || '');
  return `✓ Glob "${pattern}"`;
}

function formatGrepStatus(source: StatusSource): string {
  const query = String(source.metadata.query || source.params?.query || '');
  return `✓ Grep "${query}"`;
}

function formatWebsearchStatus(source: StatusSource): string {
  const query = String(source.metadata.query || source.params?.query || '');
  return `✓ Web search "${query}"`;
}

function formatWebfetchStatus(source: StatusSource): string {
  const url = String(source.metadata.url || source.params?.url || '');
  return `✓ Web fetch ${url}`;
}

function formatBashStatus(source: StatusSource): string {
  const durSec =
    typeof source.metadata.duration_ms === 'number'
      ? Math.max(1, Math.floor(source.metadata.duration_ms / 1000))
      : 0;
  const duration = durSec > 0 ? ` (${formatDuration(durSec * 1000)})` : '';
  return `✓ Ran command${duration}`;
}

function formatBackgroundStatus(source: StatusSource): string {
  const job = jobIdFrom(source.metadata);
  return `⚡ Launch background task${job ? ` #${job}` : ''}`;
}

function formatJobOutputStatus(source: StatusSource): string {
  const job = jobIdFrom(source.metadata);
  return `✓ Read background logs${job ? ` (#${job})` : ''}`;
}

function formatJobKillStatus(source: StatusSource): string {
  const job = jobIdFrom(source.metadata);
  return `✗ Cancel background task${job ? ` (#${job})` : ''}`;
}

function formatLspDefinitionStatus(source: StatusSource): string {
  const definitions = Array.isArray(source.metadata.definitions) ? source.metadata.definitions : [];
  const first = definitions[0] as Record<string, unknown> | undefined;
  const loc =
    first?.file
      ? `  ${first.file}:${Number(first.line || 0) + 1}:${Number(first.character || 0) + 1}`
      : '';
  return `✓ Inspect definition${loc}`;
}

function formatLspDiagnosticsStatus(source: StatusSource): string {
  const { errors, warnings } = countLspDiagnostics(source.metadata);
  const count =
    errors + warnings > 0
      ? ` (${errors} error${errors === 1 ? '' : 's'}, ${warnings} warning${warnings === 1 ? '' : 's'})`
      : '';
  return `✓ Lint diagnostics${count}`;
}

function formatLspRenameStatus(source: StatusSource): string {
  const newName = String(source.metadata.new_name || source.params?.new_name || '');
  return `● Rename symbol${newName ? ` → ${newName}` : ''}`;
}

function formatAgentStatus(_source: StatusSource): string {
  return '◈ Delegate to agent';
}

function formatTodoStatus(source: StatusSource): string {
  const taskId = String(source.metadata.task_id || '');
  return `✓ Track task${taskId ? ` #${taskId}` : ''}`;
}

function formatMcpStatus(source: StatusSource): string {
  const tool = String(source.metadata.tool || '');
  const server = String(source.metadata.server || '');
  const parts: string[] = [];
  if (server) parts.push(server);
  if (tool) parts.push(tool);
  return `⚡ MCP action ${parts.join('/')}`.trim();
}

export function getToolStepStatusText(event: {
  tool: string;
  success: boolean;
  error: string;
  metadata: Record<string, unknown>;
  params?: Record<string, unknown>;
}): string {
  if (!event.success) {
    return `✗ Failed`;
  }

  if (event.tool === GET_TOOL_DEFINITION_TOOL) {
    const toolName = String(event.metadata.tool_name || '');
    return toolName ? `✓ Loaded tool definition ${toolName}` : `✓ Loaded tool definition`;
  }
  if (event.tool === DISCOVER_CAPABILITIES_TOOL) {
    const count = typeof event.metadata.count === 'number' ? event.metadata.count : undefined;
    return `✓ Discovered capabilities${count !== undefined ? ` (${count})` : ''}`;
  }

  switch (event.tool) {
    case FILE_WRITE_TOOL:
    case 'create_file':
    case 'write_file':
      return formatFileWriteStatus(event);
    case FILE_EDIT_TOOL:
    case MULTI_EDIT_TOOL:
    case 'edit_file':
      return formatFileEditStatus(event);
    case FILE_DELETE_TOOL:
    case 'delete_file':
      return formatFileDeleteStatus(event);
    case FILE_READ_TOOL:
    case 'read_file':
      return formatFileReadStatus(event);
    case LIST_DIR_TOOL:
      return formatListDirStatus(event);
    case 'glob':
      return formatGlobStatus(event);
    case 'grep':
    case 'grep_search':
      return formatGrepStatus(event);
    case WEBSEARCH_TOOL:
      return formatWebsearchStatus(event);
    case WEBFETCH_TOOL:
      return formatWebfetchStatus(event);
    case BASH_TOOL:
    case EXECUTE_TOOL:
    case RUN_COMMAND_TOOL:
    case TERMINAL_TOOL:
      return formatBashStatus(event);
    case BACKGROUND_TOOL:
      return formatBackgroundStatus(event);
    case JOB_OUTPUT_TOOL:
      return formatJobOutputStatus(event);
    case JOB_KILL_TOOL:
      return formatJobKillStatus(event);
    case LSP_DEFINITION_TOOL:
      return formatLspDefinitionStatus(event);
    case LSP_DIAGNOSTICS_TOOL:
      return formatLspDiagnosticsStatus(event);
    case LSP_RENAME_TOOL:
      return formatLspRenameStatus(event);
    case AGENT_TOOL:
    case AGENT_TOOL_ALIAS:
      return formatAgentStatus(event);
    case TODO_TOOL:
      return formatTodoStatus(event);
    default:
      if (event.tool.startsWith('mcp_')) return formatMcpStatus(event);
      return `✓ ${getToolVerbLabel(event.tool)}`;
  }
}

/** Header shown while a step is pending: `<verb> <target>...`. */
export function getToolStepPendingText(
  tool: string,
  params: Record<string, unknown>,
  _text?: string,
): string {
  const primary = getToolStepPrimaryParam(tool, params);
  const verb = getToolVerbLabel(tool);
  return `${verb}${primary ? ` ${primary.value}` : ''}...`;
}
