export interface ContextFile {
  name: string;
  size: string;
  isDirectory: boolean;
  children?: ContextFile[];
}

export const CONTEXT_DATA: ContextFile[] = [
  {
    name: 'src/',
    size: '',
    isDirectory: true,
    children: [
      { name: 'App.tsx', size: '5.1 KB', isDirectory: false },
      { name: 'index.tsx', size: '104 B', isDirectory: false },
      {
        name: 'components/',
        size: '',
        isDirectory: true,
        children: [
          { name: 'RoundedBox.tsx', size: '1.8 KB', isDirectory: false },
          { name: 'Mascot.tsx', size: '332 B', isDirectory: false },
        ],
      },
    ],
  },
];

export const CONTEXT_META = {
  title: 'Workspace Context',
  loadedHint: '(Loaded files available to Zenith)',
  totalContextLabel: 'Total Context Size: 7.3 KB / 128 KB',
} as const;
