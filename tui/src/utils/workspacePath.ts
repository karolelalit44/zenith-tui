import * as fs from 'node:fs';
import path from 'node:path';

/** Normalize file or directory paths to use uniform forward slashes. */
export function normalizePath(inputPath?: string): string {
  if (!inputPath) return '';
  return inputPath.replace(/\\/g, '/').replace(/\/+/g, '/').trim();
}

/** Resolves the true workspace root directory from which the application was launched. */
export function resolveWorkspaceRoot(inputPath?: string): string {
  if (inputPath?.trim()) {
    return path.resolve(inputPath.trim());
  }
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

/** Extract the production-grade root workspace folder name.
 *
 * Resolves paths reliably across Windows and Unix filesystems, automatically handling
 * subpackage directories (e.g. `tui`, `server`, `packages`) to return the true root project name.
 */
export function getWorkspaceFolderName(workspacePath?: string): string {
  const target = resolveWorkspaceRoot(workspacePath);
  const normalized = normalizePath(target);
  const segments = normalized.split('/').filter(Boolean);

  if (segments.length === 0) return 'workspace';

  const lastSegment = segments[segments.length - 1];

  // If invoked inside a workspace subpackage (e.g. 'tui' or 'server'), resolve parent project root
  if (['tui', 'server', 'client', 'packages'].includes(lastSegment.toLowerCase()) && segments.length > 1) {
    return segments[segments.length - 2];
  }

  return lastSegment;
}

/** Convert an absolute or mixed-separator path to workspace-relative for display.
 *  Keeps already-relative paths normalized; absolute paths under the workspace are
 *  stripped to `server/...`, others are shortened to last 2 segments to avoid
 *  leaking `D:/vdo/...` in the timeline.
 */
export function toWorkspaceRelative(inputPath: string, workspaceRoot?: string): string {
  if (!inputPath) return '';
  const normalized = normalizePath(inputPath);
  if (!workspaceRoot) {
    // No workspace context — if absolute, shorten to last 2 segments
    if (/^[a-zA-Z]:\//.test(normalized) || normalized.startsWith('/')) {
      const parts = normalized.split('/').filter(Boolean);
      if (parts.length > 2) return parts.slice(-2).join('/');
      return normalized;
    }
    return normalized;
  }
  const wsNormalized = normalizePath(workspaceRoot);
  const lowerNorm = normalized.toLowerCase();
  const lowerWs = wsNormalized.toLowerCase();
  if (lowerNorm.startsWith(lowerWs + '/')) {
    const rel = normalized.slice(wsNormalized.length + 1);
    return rel || './';
  }
  // Also try parent of tui/server subpackage
  const wsParent = normalizePath(path.dirname(wsNormalized));
  if (wsParent && lowerNorm.startsWith(wsParent.toLowerCase() + '/')) {
    const rel = normalized.slice(wsParent.length + 1);
    // Only use if it looks like a workspace file (starts with server/, tui/, etc.)
    if (/^(server|tui|scripts|posts|ISSUE)\//i.test(rel)) return rel;
  }
  if (/^[a-zA-Z]:\//.test(normalized) || normalized.startsWith('/')) {
    const parts = normalized.split('/').filter(Boolean);
    if (parts.length > 2) return parts.slice(-2).join('/');
    return normalized;
  }
  return normalized;
}
