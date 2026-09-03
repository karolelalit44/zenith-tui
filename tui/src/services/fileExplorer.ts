import * as fs from 'node:fs';
import * as path from 'node:path';
export interface FileNode {
  name: string;
  relativePath: string;
  isDir: boolean;
  sizeFormatted?: string;
  modifiedDate?: string;
  fileType?: string;
  parentPath?: string;
}

/** Resolves the true workspace root directory from which the application was launched. */
export function resolveWorkspaceRoot(): string {
  const cwd = path.resolve(process.cwd());
  const base = path.basename(cwd).toLowerCase();
  if (['tui', 'server', 'client', 'packages'].includes(base)) {
    if (process.env.INIT_CWD && fs.existsSync(process.env.INIT_CWD)) {
      return path.resolve(process.env.INIT_CWD);
    }
    const parent = path.dirname(cwd);
    if (fs.existsSync(parent)) {
      return parent;
    }
  }
  return cwd;
}

export const workspaceRoot: string = resolveWorkspaceRoot();

/** Maximum depth for recursive searches. */
export const SEARCH_MAX_DEPTH = 6;
/** Maximum number of results returned by a search. */
export const SEARCH_MAX_RESULTS = 200;
/** Maximum entries listed in a single directory before we note truncation. */
export const LIST_MAX_ENTRIES = 1000;

const DEFAULT_IGNORED: string[] = [
  '.git',
  '.svn',
  '.hg',
  '.idea',
  '.vscode',
  'node_modules',
  'dist',
  'build',
  '.next',
  '.turbo',
  '.venv',
  'venv',
  '__pycache__',
  '.pytest_cache',
  '.mypy_cache',
  '.mypy',
  '.ruff_cache',
  '.tox',
  '.cache',
  'coverage',
  'htmlcov',
  '.nyc_output',
  '.zenith',
  '.agents',
  '.claude',
  '.freebuff',
  'test_snapshots',
  'ref_repo',
  'data',
];

const BINARY_EXTENSIONS = new Set([
  '.png',
  '.jpg',
  '.jpeg',
  '.gif',
  '.webp',
  '.ico',
  '.svg',
  '.pdf',
  '.zip',
  '.gz',
  '.tar',
  '.7z',
  '.exe',
  '.dll',
  '.so',
  '.dylib',
  '.wasm',
  '.pyc',
  '.woff',
  '.woff2',
  '.ttf',
  '.otf',
  '.mp3',
  '.mp4',
  '.mov',
  '.avi',
  '.bin',
  '.dat',
  '.db',
  '.sqlite',
  '.woff',
  '.map',
]);

const FILE_TYPE_LABELS: Record<string, string> = {
  '.json': 'JSON',
  '.jsonc': 'JSON',
  '.js': 'JavaScript',
  '.jsx': 'React JSX',
  '.mjs': 'JavaScript',
  '.cjs': 'JavaScript',
  '.ts': 'TypeScript',
  '.tsx': 'React TSX',
  '.mts': 'TypeScript',
  '.cts': 'TypeScript',
  '.py': 'Python',
  '.md': 'Markdown',
  '.mdx': 'Markdown',
  '.txt': 'Text',
  '.toml': 'TOML',
  '.yaml': 'YAML',
  '.yml': 'YAML',
  '.html': 'HTML',
  '.htm': 'HTML',
  '.css': 'CSS',
  '.scss': 'SCSS',
  '.less': 'LESS',
  '.sh': 'Shell',
  '.bash': 'Shell',
  '.zsh': 'Shell',
  '.rs': 'Rust',
  '.go': 'Go',
  '.c': 'C',
  '.h': 'C Header',
  '.cpp': 'C++',
  '.hpp': 'C++ Header',
  '.cs': 'C#',
  '.java': 'Java',
  '.kt': 'Kotlin',
  '.swift': 'Swift',
  '.rb': 'Ruby',
  '.php': 'PHP',
  '.sql': 'SQL',
  '.csv': 'CSV',
  '.xml': 'XML',
  '.vue': 'Vue',
  '.svelte': 'Svelte',
  '.svg': 'SVG',
};

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function formatModified(mtimeMs: number): string {
  const d = new Date(mtimeMs);
  const now = new Date();
  const sameYear = d.getFullYear() === now.getFullYear();
  const opts: Intl.DateTimeFormatOptions = sameYear
    ? { month: 'short', day: 'numeric' }
    : { month: 'short', day: 'numeric', year: 'numeric' };
  return d.toLocaleDateString(undefined, opts);
}

function labelForPath(relPath: string, isDir: boolean): string {
  if (isDir) return 'Folder';
  return FILE_TYPE_LABELS[path.extname(relPath).toLowerCase()] ?? 'File';
}

/** Minimal gitignore-style matcher. Supports comments, negations, dir-pins and * wildcards. */
class IgnoreMatcher {
  private patterns: { positive: boolean; re: RegExp }[] = [];

  constructor(patterns: string[]) {
    for (const raw of patterns) {
      const trimmed = raw.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      let positive = true;
      let p = trimmed;
      if (p.startsWith('!')) {
        positive = false;
        p = p.slice(1);
      }
      const dirPinned = p.endsWith('/');
      const candidate = dirPinned ? p.slice(0, -1) : p;
      const escapedBase = candidate
        .replace(/[.+?^${}()|[\]\\]/g, '\\$&')
        .replace(/\*\*/g, '\u0000')
        .replace(/\*/g, '[^/]*')
        .replace(/\u0000/g, '.*');
      // Match both the path segment and anything containing it as a directory.
      const re = new RegExp(`(^|/)${escapedBase}(/|$)`);
      this.patterns.push({ positive, re });
    }
  }

  /** Returns true when the path should be ignored. */
  isIgnored(relPath: string): boolean {
    let ignored = false;
    for (const { positive, re } of this.patterns) {
      // A matching positive (ignore) pattern marks the path ignored; a
      // matching negative ("!") pattern un-ignores it.
      if (re.test(relPath)) ignored = positive;
    }
    return ignored;
  }
}

let cachedMatcher: IgnoreMatcher | null = null;

function getMatcher(): IgnoreMatcher {
  if (cachedMatcher) return cachedMatcher;
  const extra: string[] = [];
  try {
    const ignorePath = path.join(workspaceRoot, '.zenithignore');
    if (fs.existsSync(ignorePath)) {
      const content = fs.readFileSync(ignorePath, 'utf-8');
      for (const line of content.split(/\r?\n/)) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;
        extra.push(trimmed);
      }
    }
  } catch {
    /* ignore */
  }
  cachedMatcher = new IgnoreMatcher([...DEFAULT_IGNORED, ...extra]);
  return cachedMatcher;
}

function isBinary(relativePath: string): boolean {
  return BINARY_EXTENSIONS.has(path.extname(relativePath).toLowerCase());
}

/** Build a FileNode from a directory entry. */
function nodeFromEntry(fullPath: string, relativePath: string, isDir: boolean): FileNode {
  let sizeFormatted: string | undefined;
  let modifiedDate: string | undefined;
  try {
    const stat = fs.statSync(fullPath);
    modifiedDate = formatModified(stat.mtimeMs);
    if (!isDir) sizeFormatted = formatBytes(stat.size);
  } catch {
    /* leave blank */
  }
  const parts = relativePath.split('/');
  const name = parts[parts.length - 1] || relativePath;
  const parentPath = parts.slice(0, -1).join('/');
  return {
    name,
    relativePath,
    isDir,
    sizeFormatted: isDir ? undefined : sizeFormatted,
    modifiedDate,
    fileType: labelForPath(relativePath, isDir),
    parentPath: parentPath || undefined,
  };
}

/** List the immediate children of a directory (real filesystem). */
export function getDirectoryContents(parentPath: string): FileNode[] {
  const base = path.resolve(workspaceRoot, parentPath || '.');
  try {
    if (!fs.existsSync(base) || !fs.statSync(base).isDirectory()) return [];
    const entries = fs.readdirSync(base, { withFileTypes: true });
    const matcher = getMatcher();
    const nodes: FileNode[] = [];
    for (const entry of entries) {
      const rel = parentPath ? `${parentPath}/${entry.name}` : entry.name;
      if (matcher.isIgnored(rel)) continue;
      const full = path.join(base, entry.name);
      const isDir = entry.isDirectory();
      if (!isDir && isBinary(rel)) continue;
      nodes.push(nodeFromEntry(full, rel, isDir));
      if (nodes.length >= LIST_MAX_ENTRIES) break;
    }
    nodes.sort((a, b) => {
      if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    if (parentPath && parentPath.trim().length > 0) {
      const parts = parentPath.split('/').filter(Boolean);
      parts.pop();
      const parentRel = parts.join('/');
      nodes.unshift({
        name: '..',
        relativePath: parentRel,
        isDir: true,
        fileType: 'Folder',
        sizeFormatted: '—',
        modifiedDate: '—',
      });
    }
    return nodes;
  } catch {
    return [];
  }
}

function walkForSearch(dirPath: string, relPrefix: string, q: string, depth: number, results: FileNode[]): void {
  if (depth > SEARCH_MAX_DEPTH || results.length >= SEARCH_MAX_RESULTS) return;
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dirPath, { withFileTypes: true });
  } catch {
    return;
  }
  const matcher = getMatcher();
  const sorted = entries.slice().sort((a, b) => {
    if (a.isDirectory() !== b.isDirectory()) return a.isDirectory() ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  for (const entry of sorted) {
    if (results.length >= SEARCH_MAX_RESULTS) return;
    const rel = relPrefix ? `${relPrefix}/${entry.name}` : entry.name;
    if (matcher.isIgnored(rel)) continue;
    const full = path.join(dirPath, entry.name);
    const isDir = entry.isDirectory();
    const haystack = rel.toLowerCase();
    const matches = haystack.includes(q);
    if (!isDir && isBinary(rel)) continue;
    if (isDir) {
      if (matches && rel.includes(q)) {
        results.push(nodeFromEntry(full, rel, true));
      }
      if (depth < SEARCH_MAX_DEPTH) {
        walkForSearch(full, rel, q, depth + 1, results);
      }
    } else if (matches) {
      results.push(nodeFromEntry(full, rel, false));
    }
  }
}

/** Bounded recursive search of the workspace, honoring ignore rules. */
export function searchFiles(query: string): FileNode[] {
  const trimmed = query.trim();
  if (!trimmed) {
    try {
      if (!fs.existsSync(workspaceRoot)) return [];
    } catch {
      return [];
    }
    return getDirectoryContents('');
  }
  const q = trimmed.toLowerCase();
  const results: FileNode[] = [];
  walkForSearch(workspaceRoot, '', q, 0, results);
  // Prioritize shallow, file matches.
  results.sort((a, b) => {
    const aDepth = a.relativePath.split('/').length;
    const bDepth = b.relativePath.split('/').length;
    if (aDepth !== bDepth) return aDepth - bDepth;
    if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
    return a.relativePath.localeCompare(b.relativePath);
  });
  return results.slice(0, SEARCH_MAX_RESULTS);
}

/**
 * Compatibility list of selectable workspace files (non-dirs) for the ContextModal
 * sample view and other consumers that relied on the legacy static list.
 */
export function collectWorkspaceFiles(): FileNode[] {
  const results: FileNode[] = [];
  const collect = (dirPath: string, relPrefix: string, depth: number): void => {
    if (depth > 3 || results.length >= 50) return;
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dirPath, { withFileTypes: true });
    } catch {
      return;
    }
    const matcher = getMatcher();
    for (const entry of entries) {
      if (results.length >= 50) return;
      const rel = relPrefix ? `${relPrefix}/${entry.name}` : entry.name;
      if (matcher.isIgnored(rel)) continue;
      const full = path.join(dirPath, entry.name);
      if (entry.isDirectory()) {
        collect(full, rel, depth + 1);
      } else if (!isBinary(rel)) {
        results.push(nodeFromEntry(full, rel, false));
      }
    }
  };
  try {
    collect(workspaceRoot, '', 0);
  } catch {
    /* ignore */
  }
  return results;
}

/** Legacy constant — computed lazily from the real filesystem when first accessed. */
export const WORKSPACE_FILES: FileNode[] = (() => {
  try {
    return collectWorkspaceFiles();
  } catch {
    return [];
  }
})();
