export interface PluginTab {
  id: string;
  label: string;
}

export const PLUGIN_TABS: PluginTab[] = [
  { id: 'discover', label: 'Discover' },
  { id: 'installed', label: 'Installed' },
  { id: 'marketplaces', label: 'Marketplaces' },
  { id: 'errors', label: 'Errors' },
];

export interface PluginItem {
  name: string;
  source: string;
  installs: string;
  description: string;
}

export const PLUGIN_LIST: PluginItem[] = [
  {
    name: 'context7',
    source: 'zenith-plugins-official [Community Managed]',
    installs: '36.2K',
    description: 'Upstash Context7 MCP server for up-to-date documentation ...',
  },
];

export const PLUGINS_META = {
  title: 'Zenith Plugins',
  headerLabel: 'plugins',
  hotkeys: {
    cycle: 'arrows to cycle',
    run: 'enter to run',
    close: 'esc to close',
  },
  searchLabel: '⌕ Search: ',
} as const;
