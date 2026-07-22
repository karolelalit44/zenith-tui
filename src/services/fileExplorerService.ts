export interface FileNode {
  name: string;
  relativePath: string;
  isDir: boolean;
  sizeFormatted?: string;
  modifiedDate?: string;
  fileType?: string;
  parentPath?: string;
}

export const WORKSPACE_FILES: FileNode[] = [
  // Root Level Folders
  { name: 'src', relativePath: 'src', isDir: true, fileType: 'Folder', parentPath: '' },
  { name: 'public', relativePath: 'public', isDir: true, fileType: 'Folder', parentPath: '' },
  { name: 'tests', relativePath: 'tests', isDir: true, fileType: 'Folder', parentPath: '' },

  // Root Level Files
  { name: 'package.json', relativePath: 'package.json', isDir: false, sizeFormatted: '2.1 KB', modifiedDate: 'Jul 20, 2026', fileType: 'JSON', parentPath: '' },
  { name: 'tsconfig.json', relativePath: 'tsconfig.json', isDir: false, sizeFormatted: '1.4 KB', modifiedDate: 'Jul 18, 2026', fileType: 'JSON', parentPath: '' },
  { name: 'README.md', relativePath: 'README.md', isDir: false, sizeFormatted: '5.8 KB', modifiedDate: 'Jul 18, 2026', fileType: 'Markdown', parentPath: '' },
  { name: 'vite.config.ts', relativePath: 'vite.config.ts', isDir: false, sizeFormatted: '1.1 KB', modifiedDate: 'Jul 19, 2026', fileType: 'TypeScript', parentPath: '' },

  // src Subfolders
  { name: 'components', relativePath: 'src/components', isDir: true, fileType: 'Folder', parentPath: 'src' },
  { name: 'screens', relativePath: 'src/screens', isDir: true, fileType: 'Folder', parentPath: 'src' },
  { name: 'services', relativePath: 'src/services', isDir: true, fileType: 'Folder', parentPath: 'src' },
  { name: 'theme', relativePath: 'src/theme', isDir: true, fileType: 'Folder', parentPath: 'src' },
  { name: 'utils', relativePath: 'src/utils', isDir: true, fileType: 'Folder', parentPath: 'src' },
  { name: 'App.tsx', relativePath: 'src/App.tsx', isDir: false, sizeFormatted: '7.6 KB', modifiedDate: 'Jul 22, 2026', fileType: 'React TSX', parentPath: 'src' },
  { name: 'index.ts', relativePath: 'src/index.ts', isDir: false, sizeFormatted: '0.4 KB', modifiedDate: 'Jul 18, 2026', fileType: 'TypeScript', parentPath: 'src' },

  // src/components Subfolders & Files
  { name: 'Display', relativePath: 'src/components/Display', isDir: true, fileType: 'Folder', parentPath: 'src/components' },
  { name: 'Input', relativePath: 'src/components/Input', isDir: true, fileType: 'Folder', parentPath: 'src/components' },
  { name: 'ui', relativePath: 'src/components/ui', isDir: true, fileType: 'Folder', parentPath: 'src/components' },

  // src/components/Input Files
  { name: 'InputBox.tsx', relativePath: 'src/components/Input/InputBox.tsx', isDir: false, sizeFormatted: '18.4 KB', modifiedDate: 'Jul 22, 2026', fileType: 'React TSX', parentPath: 'src/components/Input' },
  { name: 'AutocompleteDropdown.tsx', relativePath: 'src/components/Input/AutocompleteDropdown.tsx', isDir: false, sizeFormatted: '2.4 KB', modifiedDate: 'Jul 22, 2026', fileType: 'React TSX', parentPath: 'src/components/Input' },

  // src/utils Files
  { name: 'syntaxHighlight.ts', relativePath: 'src/utils/syntaxHighlight.ts', isDir: false, sizeFormatted: '2.8 KB', modifiedDate: 'Jul 22, 2026', fileType: 'TypeScript', parentPath: 'src/utils' },

  // src/screens/Welcome Files
  { name: 'WelcomeScreen.tsx', relativePath: 'src/screens/Welcome/WelcomeScreen.tsx', isDir: false, sizeFormatted: '4.5 KB', modifiedDate: 'Jul 22, 2026', fileType: 'React TSX', parentPath: 'src/screens/Welcome' },

  // tests Files
  { name: 'App.test.tsx', relativePath: 'tests/App.test.tsx', isDir: false, sizeFormatted: '4.2 KB', modifiedDate: 'Jul 22, 2026', fileType: 'TypeScript Test', parentPath: 'tests' },
];

export function getDirectoryContents(parentPath: string): FileNode[] {
  return WORKSPACE_FILES.filter(f => f.parentPath === parentPath);
}

export function searchFiles(query: string): FileNode[] {
  if (!query.trim()) return WORKSPACE_FILES;
  const q = query.toLowerCase();
  return WORKSPACE_FILES.filter(f => f.name.toLowerCase().includes(q) || f.relativePath.toLowerCase().includes(q));
}
