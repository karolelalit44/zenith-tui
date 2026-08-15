import path from 'node:path';

/** Normalize file or directory paths to use uniform forward slashes. */
export function normalizePath(inputPath?: string): string {
  if (!inputPath) return '';
  return inputPath.replace(/\\/g, '/').replace(/\/+/g, '/').trim();
}

/** Extract the production-grade root workspace folder name.
 *
 * Resolves paths reliably across Windows and Unix filesystems, automatically handling
 * subpackage directories (e.g. `tui`, `server`, `packages`) to return the true root project name.
 */
export function getWorkspaceFolderName(workspacePath?: string): string {
  const target = workspacePath?.trim() ? path.resolve(workspacePath) : process.cwd();
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
