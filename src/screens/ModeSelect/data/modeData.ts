export interface ModeOption {
  id: string;
  label: string;
  icon: string;
  desc: string;
}

export const MODE_OPTIONS: ModeOption[] = [
  { id: 'plan', label: 'Plan', icon: '◇', desc: 'Analyze the request and create an execution plan without making changes.' },
  { id: 'build', label: 'Build', icon: '◆', desc: 'Execute the full build flow: think, create files, run commands, and deliver.' },
];

export const MODE_META = {
  title: 'Select Mode',
  headerLabel: 'CHOOSE OPERATING MODE',
  hotkeys: {
    navigate: '[↑↓] Navigate',
    select: '[↵] Select',
    close: '[Esc] Close',
  },
} as const;
