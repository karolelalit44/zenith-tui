import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FileNode } from '../src/services/fileExplorer';

const ORIG_CWD = process.cwd();

let tmp: string;
let mod: {
  getDirectoryContents: (p: string) => FileNode[];
  searchFiles: (q: string) => FileNode[];
};

beforeEach(async () => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'zenith-fs-'));
  process.chdir(tmp);
  fs.mkdirSync(path.join(tmp, 'src', 'auth'), { recursive: true });
  fs.mkdirSync(path.join(tmp, 'src', 'utils'), { recursive: true });
  fs.mkdirSync(path.join(tmp, 'node_modules'), { recursive: true });
  fs.mkdirSync(path.join(tmp, '.git'), { recursive: true });
  fs.writeFileSync(path.join(tmp, 'src', 'auth', 'login.ts'), 'export const login = 1;\n');
  fs.writeFileSync(path.join(tmp, 'src', 'auth', 'session.ts'), 'export const session = 1;\n');
  fs.writeFileSync(path.join(tmp, 'src', 'utils', 'format.ts'), 'export const format = 1;\n');
  fs.writeFileSync(path.join(tmp, 'README.md'), '# readme\n');
  fs.writeFileSync(path.join(tmp, 'node_modules', 'dep.js'), 'ignored\n');
  fs.writeFileSync(path.join(tmp, '.git', 'config'), 'ignored\n');
  vi.resetModules();
  mod = await import('../src/services/fileExplorer');
});

afterEach(() => {
  process.chdir(ORIG_CWD);
  fs.rmSync(tmp, { recursive: true, force: true });
});

describe('getDirectoryContents', () => {
  it('lists top-level files and folders, dirs first, ignoring node_modules/.git', () => {
    const items = mod.getDirectoryContents('');
    const names = items.map((i) => `${i.isDir ? 'DIR' : 'FILE'}:${i.name}`);
    expect(names).toContain('DIR:src');
    expect(names).toContain('FILE:README.md');
    expect(names).not.toContain('DIR:node_modules');
    expect(names).not.toContain('DIR:.git');
    expect(names.indexOf('DIR:src')).toBeLessThan(names.indexOf('FILE:README.md'));
  });

  it('lists children of a nested directory', () => {
    const items = mod.getDirectoryContents('src/auth');
    const names = items.map((i) => i.name);
    expect(names).toContain('login.ts');
    expect(names).toContain('session.ts');
  });
});

describe('searchFiles', () => {
  it('searches recursively by name', () => {
    const results = mod.searchFiles('login');
    expect(results.map((r) => r.name)).toContain('login.ts');
  });

  it('does not descend into ignored directories', () => {
    const results = mod.searchFiles('dep');
    expect(results.map((r) => r.name)).not.toContain('dep.js');
  });

  it('returns empty for a query with no matches', () => {
    const results = mod.searchFiles('zzz-no-such-file');
    expect(results).toEqual([]);
  });
});
