export interface ThemeOption {
  id: string;
  label: string;
  icon: string;
  desc: string;
}

export const THEME_OPTIONS: ThemeOption[] = [
  { id: 'deep_forest', label: 'Deep Forest', icon: '🌲', desc: 'Default dark green and ethereal hues.' },
  { id: 'synthwave', label: 'Synthwave', icon: '🌆', desc: 'Neon pinks, purples, and retrowave styling.' },
  { id: 'monokai', label: 'Monokai Pro', icon: '🎨', desc: 'Vibrant, high-contrast editor colors.' },
  { id: 'dracula', label: 'Dracula', icon: '🧛', desc: 'A dark theme for vampires.' },
  { id: 'aura', label: 'Aura', icon: '✨', desc: 'Soft pastel gradients with a modern feel.' },
  { id: 'graphite', label: 'Graphite Monochrome', icon: '⚙️', desc: 'Sleek, low-profile, grayscale aesthetic.' },
];

export const THEME_META = {
  title: 'Theme Engine',
  headerLabel: 'SELECT UI THEME',
  activeBadge: '● ACTIVE',
  hotkeys: {
    navigate: '[↑↓] Navigate',
    apply: '[↵] Apply Theme',
    close: '[Esc] Close',
  },
} as const;
