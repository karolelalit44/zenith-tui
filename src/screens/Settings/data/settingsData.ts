export interface SettingItem {
  id: string;
  label: string;
  icon: string;
  desc: string;
  actionType: 'navigate' | 'toggle';
}

export const SETTINGS_DATA: SettingItem[] = [
  {
    id: 'theme',
    label: 'Theme Configuration',
    icon: '◨',
    desc: 'Open theme editor to customize UI colors and appearance.',
    actionType: 'navigate',
  },
  {
    id: 'autoApprove',
    label: 'Auto-Approve Edits',
    icon: '⚡',
    desc: 'Automatically execute AI-suggested code changes without prompting.',
    actionType: 'toggle',
  },
];

export const SETTINGS_META = {
  title: 'System Settings',
  headerLabel: 'CONFIGURE SYSTEM SETTINGS',
  hotkeys: {
    navigate: '[↑↓] Navigate',
    toggle: '[↵] Toggle/Select',
    close: '[Esc] Close',
  },
} as const;
