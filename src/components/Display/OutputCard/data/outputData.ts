import { OutputKind } from '../types';

export const KIND_META: Record<OutputKind, { icon: string; colorKey: 'emerald' | 'warning' | 'error' | 'ethereal' }> = {
  file_edit:    { icon: '✎', colorKey: 'emerald' },
  file_created: { icon: '✦', colorKey: 'emerald' },
  file_deleted: { icon: '✖', colorKey: 'error' },
  message:      { icon: '●', colorKey: 'ethereal' },
  build_result: { icon: '⬡', colorKey: 'warning' },
  tool_result:  { icon: '◆', colorKey: 'emerald' },
  error:        { icon: '✗', colorKey: 'error' },
};

export const STATUS_META = {
  success: { label: 'DONE', colorKey: 'emerald' as const },
  warning: { label: 'WARN', colorKey: 'warning' as const },
  error:   { label: 'FAIL', colorKey: 'error' as const },
  info:    { label: 'INFO', colorKey: 'ethereal' as const },
} as const;
