export const FILE_WRITE_TOOL = 'file_write';
export const FILE_EDIT_TOOL = 'file_edit';
export const FILE_DELETE_TOOL = 'file_delete';
export const FILE_READ_TOOL = 'file_read';
export const BASH_TOOL = 'bash';
export const EXECUTE_TOOL = 'execute';
export const RUN_COMMAND_TOOL = 'run_command';
export const GET_TOOL_DEFINITION_TOOL = 'get_tool_definition';

export const TOOL_VERB_LABELS: Record<string, string> = {
  [FILE_WRITE_TOOL]: 'Create',
  [FILE_EDIT_TOOL]: 'Update',
  multi_edit: 'Update',
  [FILE_DELETE_TOOL]: 'Delete',
  [FILE_READ_TOOL]: 'Read',
  list_dir: 'List',
  glob: 'Search',
  grep: 'Search',
  grep_search: 'Search',
  websearch: 'Search',
  [BASH_TOOL]: 'Run',
  [EXECUTE_TOOL]: 'Run',
  [RUN_COMMAND_TOOL]: 'Run',
  [GET_TOOL_DEFINITION_TOOL]: 'Load',
  discover_capabilities: 'Discover',
  lsp_definition: 'Inspect',
  lsp_diagnostics: 'Diagnose',
  lsp_rename: 'Rename',
  job_output: 'Inspect',
  job_kill: 'Kill',
  webfetch: 'Fetch',
  todo: 'Track',
  agent: 'Delegate',
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

export const TOOL_STEP_PRIMARY_KEYS = ['path', 'filepath', 'command', 'url', 'query', 'pattern', 'glob'] as const;

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

export function getToolStepStatusText(event: {
  tool: string;
  success: boolean;
  error: string;
  metadata: Record<string, unknown>;
}): string {
  if (!event.success) {
    return `✗ Failed`;
  }

  if (event.tool === GET_TOOL_DEFINITION_TOOL) {
    const toolName = String(event.metadata.tool_name || '');
    return toolName ? `✓ Loaded tool definition ${toolName}` : `✓ Loaded tool definition`;
  }

  const verb = TOOL_VERB_LABELS[event.tool] || 'Executed';

  switch (event.tool) {
    case FILE_WRITE_TOOL: {
      const path = String(event.metadata.path || '');
      const size = typeof event.metadata.size === 'number' ? `${event.metadata.size} B` : '';
      return `✓ ${verb}${path ? ` ${path}` : ''}${size ? ` (${size})` : ''}`;
    }
    case FILE_EDIT_TOOL: {
      const path = String(event.metadata.path || '');
      return `✓ ${verb}${path ? ` ${path}` : ''}`;
    }
    case FILE_DELETE_TOOL: {
      const path = String(event.metadata.path || '');
      return `✓ ${verb}${path ? ` ${path}` : ''}`;
    }
    case FILE_READ_TOOL: {
      const path = String(event.metadata.path || '');
      const lines = typeof event.metadata.lines === 'number' ? `${event.metadata.lines} lines` : '';
      return `✓ ${verb}${path ? ` ${path}` : ''}${lines ? ` (${lines})` : ''}`;
    }
    case BASH_TOOL:
    case EXECUTE_TOOL:
    case RUN_COMMAND_TOOL: {
      const duration =
        typeof event.metadata.duration_ms === 'number' ? ` (${(event.metadata.duration_ms / 1000).toFixed(1)}s)` : '';
      return `✓ Ran command${duration}`;
    }
    default:
      return `✓ ${verb}`;
  }
}
