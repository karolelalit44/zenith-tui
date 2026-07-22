export interface MetricItem {
  label: string;
  value: string;
  isWarning?: boolean;
}

export const ADD_DIR_DATA = {
  headerLabel: 'WORKSPACE SYNC',
  metrics: [
    { label: 'Files Indexed', value: '1,204' },
    { label: 'Dependencies', value: '32' },
    { label: 'Context Delta', value: '+14.2 MB', isWarning: true },
    { label: 'Sync Time', value: '842ms' },
  ] as MetricItem[],
  statusMessage: 'Directory mapped and vectorized. Zenith engine is now tracking this path.',
} as const;
