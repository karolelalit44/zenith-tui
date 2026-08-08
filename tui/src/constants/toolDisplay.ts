export const FILE_WRITE_TOOL = 'file_write';
export const FILE_EDIT_TOOL = 'file_edit';
export const FILE_DELETE_TOOL = 'file_delete';
export const FILE_READ_TOOL = 'file_read';
export const BASH_TOOL = 'bash';
export const EXECUTE_TOOL = 'execute';
export const RUN_COMMAND_TOOL = 'run_command';

export const TOOL_VERB_LABELS: Record<string, string> = {
  [FILE_WRITE_TOOL]: 'Create',
  [FILE_EDIT_TOOL]: 'Update',
  [FILE_DELETE_TOOL]: 'Delete',
  [FILE_READ_TOOL]: 'Read',
};

export const TOOL_RESULT_MAX_OUTPUT_LINES = 20;
export const TOOL_RESULT_MAX_DIFF_LINES = 15;
export const TOOL_RESULT_MAX_READ_PREVIEW_LINES = 8;
export const TOOL_RESULT_MAX_DEFAULT_PREVIEW_LINES = 10;
export const TOOL_RESULT_FALLBACK_EDIT_LABEL = 'Updated file';
