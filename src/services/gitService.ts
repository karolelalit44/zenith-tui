import { execSync } from 'node:child_process';

export function getActiveGitBranch(cwd: string = process.cwd()): string {
  try {
    const branch = execSync('git branch --show-current', { cwd, encoding: 'utf-8', timeout: 1000 });
    const trimmed = branch.trim();
    return trimmed || 'main';
  } catch (_err) {
    return 'main';
  }
}
