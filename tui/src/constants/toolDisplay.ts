import { formatDuration } from '../utils/text';

export const FILE_WRITE_TOOL = 'file_write';
export const FILE_EDIT_TOOL = 'file_edit';
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
export const CREWMATE_TOOL = 'agent';
export const CREWMATE_TOOL_ALIAS = 'agent_tool';
/** WP5: model-invocable explore delegation (Apogee crewmate). */
export const EXPLORE_TOOL = 'explore';
export const TODO_TOOL = 'todo';

/** Legacy backend aliases for the canonical file tools. */
export const READ_FILE_ALIAS = 'read_file';
export const WRITE_FILE_ALIAS = 'write_file';
export const CREATE_FILE_ALIAS = 'create_file';
export const EDIT_FILE_ALIAS = 'edit_file';
export const DELETE_FILE_ALIAS = 'delete_file';
export const GREP_SEARCH_ALIAS = 'grep_search';

/**
 * Execution-timeline tool categories. Every timeline row branches on one of
 * these sets instead of re-declaring ad-hoc tool-name arrays.
 */
export const SHELL_TOOL_SET: ReadonlySet<string> = new Set([BASH_TOOL, EXECUTE_TOOL, RUN_COMMAND_TOOL, TERMINAL_TOOL]);

export const FILE_READ_TOOL_SET: ReadonlySet<string> = new Set([FILE_READ_TOOL, READ_FILE_ALIAS]);

export const SEARCH_TOOL_SET: ReadonlySet<string> = new Set(['grep', GREP_SEARCH_ALIAS, 'glob']);

export const LIST_DIR_TOOL_SET: ReadonlySet<string> = new Set([LIST_DIR_TOOL, 'ls', 'dir']);

export const FILE_MUTATION_TOOL_SET: ReadonlySet<string> = new Set([
  FILE_WRITE_TOOL,
  WRITE_FILE_ALIAS,
  CREATE_FILE_ALIAS,
  FILE_EDIT_TOOL,
  EDIT_FILE_ALIAS,
  'multi_edit',
]);

export const FILE_DELETE_TOOL_SET: ReadonlySet<string> = new Set([FILE_DELETE_TOOL, DELETE_FILE_ALIAS]);

/** Read-only tools eligible for consecutive-repeat folding (×N badge). */
export const REPEATABLE_READ_ONLY_TOOL_SET: ReadonlySet<string> = new Set([
  ...FILE_READ_TOOL_SET,
  ...SEARCH_TOOL_SET,
  ...LIST_DIR_TOOL_SET,
]);

/** Error text stamped onto a tool_call whose tool_result never arrived. */
export const INTERRUPTED_TOOL_ERROR = 'execution interrupted before completion';

/** ToolStep metadata key carrying the folded-consecutive-run count. */
export const TOOL_META_REPEAT_COUNT = 'repeatCount';

/** ToolStep metadata flag marking an execution that never completed. */
export const TOOL_META_INTERRUPTED = 'interrupted';

/** Matches cancellation/interruption phrasing in tool errors. */
export const CANCELLED_ERROR_PATTERN = /\b(cancel|interrupt|abort)/i;

export const TOOL_VERB_LABELS: Record<string, string> = {
  [FILE_WRITE_TOOL]: 'Create',
  create_file: 'Create',
  write_file: 'Create',
  [FILE_EDIT_TOOL]: 'Update',
  edit_file: 'Update',
  multi_edit: 'Update',
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
  [CREWMATE_TOOL]: 'Delegate',
  [CREWMATE_TOOL_ALIAS]: 'Delegate',
  [EXPLORE_TOOL]: 'Investigate',
  [TODO_TOOL]: 'Track',
};

export function getToolVerbLabel(tool: string): string {
  return TOOL_VERB_LABELS[tool] || tool;
}

export const TOOL_STEP_PRIMARY_KEYS = [
  'path',
  'filepath',
  'command',
  'url',
  'query',
  'pattern',
  'glob',
  'job_id',
  'task_id',
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
  return String(metadata.path || '') || String(params?.filepath || '') || String(params?.path || '');
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
  return ` Read${path ? ` ${path}` : ''}${lines !== undefined ? ` (${lines} lines)` : ''}`;
}

function formatListDirStatus(source: StatusSource): string {
  const path = pathFrom(source);
  const subdirs = typeof source.metadata.subdirs === 'number' ? source.metadata.subdirs : undefined;
  const files = typeof source.metadata.files === 'number' ? source.metadata.files : undefined;
  const parts: string[] = [];
  if (subdirs !== undefined) parts.push(`${subdirs} subdir${subdirs === 1 ? '' : 's'}`);
  if (files !== undefined) parts.push(`${files} file${files === 1 ? '' : 's'}`);
  return ` List${path ? ` ${path}` : ''}${parts.length > 0 ? ` (${parts.join(', ')})` : ''}`;
}

function formatGlobStatus(source: StatusSource): string {
  const pattern = String(source.metadata.pattern || source.params?.pattern || '');
  return ` Glob "${pattern}"`;
}

function formatGrepStatus(source: StatusSource): string {
  const query = String(source.metadata.query || source.params?.query || '');
  return ` Grep "${query}"`;
}

function formatWebsearchStatus(source: StatusSource): string {
  const query = String(source.metadata.query || source.params?.query || '');
  return ` Web search "${query}"`;
}

function formatWebfetchStatus(source: StatusSource): string {
  const url = String(source.metadata.url || source.params?.url || '');
  return ` Web fetch ${url}`;
}

function formatBashStatus(source: StatusSource): string {
  const durSec =
    typeof source.metadata.duration_ms === 'number' ? Math.max(1, Math.floor(source.metadata.duration_ms / 1000)) : 0;
  const duration = durSec > 0 ? ` (${formatDuration(durSec * 1000)})` : '';
  return ` Ran command${duration}`;
}

function formatBackgroundStatus(source: StatusSource): string {
  const job = jobIdFrom(source.metadata);
  return `⚡ Launch background task${job ? ` #${job}` : ''}`;
}

function formatJobOutputStatus(source: StatusSource): string {
  const job = jobIdFrom(source.metadata);
  return ` Read background logs${job ? ` (#${job})` : ''}`;
}

function formatJobKillStatus(source: StatusSource): string {
  const job = jobIdFrom(source.metadata);
  return `✗ Cancel background task${job ? ` (#${job})` : ''}`;
}

function formatCrewmateStatus(_source: StatusSource): string {
  return '◈ Delegate to crewmate';
}

function formatTodoStatus(source: StatusSource): string {
  const taskId = String(source.metadata.task_id || '');
  return ` Track task${taskId ? ` #${taskId}` : ''}`;
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
    return toolName ? ` Loaded tool definition ${toolName}` : ` Loaded tool definition`;
  }
  if (event.tool === DISCOVER_CAPABILITIES_TOOL) {
    const count = typeof event.metadata.count === 'number' ? event.metadata.count : undefined;
    return ` Discovered capabilities${count !== undefined ? ` (${count})` : ''}`;
  }

  switch (event.tool) {
    case FILE_WRITE_TOOL:
    case 'create_file':
    case 'write_file':
      return formatFileWriteStatus(event);
    case FILE_EDIT_TOOL:
    case 'edit_file':
    case 'multi_edit':
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
    case CREWMATE_TOOL:
    case CREWMATE_TOOL_ALIAS:
      return formatCrewmateStatus(event);
    case TODO_TOOL:
      return formatTodoStatus(event);
    default:
      return ` ${getToolVerbLabel(event.tool)}`;
  }
}
