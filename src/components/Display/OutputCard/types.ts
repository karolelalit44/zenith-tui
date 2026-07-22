import { DiffLine } from '../../../types';

export type OutputKind = 'file_edit' | 'file_created' | 'file_deleted' | 'message' | 'build_result' | 'tool_result' | 'error';

export interface OutputMeta {
  kind: OutputKind;
  icon: string;
  title: string;
  status: 'success' | 'warning' | 'error' | 'info';
  filePath?: string;
  message?: string;
  diff?: DiffLine[];
  buildSteps?: BuildStep[];
  elapsed?: string;
}

export interface BuildStep {
  label: string;
  duration: string;
  success: boolean;
}

export interface OutputCardProps {
  meta: OutputMeta;
}
