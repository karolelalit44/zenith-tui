import { execSync } from 'node:child_process';
import { appConfig } from '../config/appConfig';
import { resolveWorkspaceRoot } from '../utils/workspacePath';

let branchCache: { branch: string; timestamp: number } | null = null;

export function getActiveGitBranch(cwd: string = resolveWorkspaceRoot()): string {
  const now = Date.now();
  if (branchCache && now - branchCache.timestamp < appConfig.git.cacheTtlMs) {
    return branchCache.branch;
  }
  try {
    const branch = execSync('git branch --show-current', {
      cwd,
      encoding: 'utf-8',
      timeout: appConfig.git.timeoutMs,
    });
    const trimmed = branch.trim();
    const result = trimmed || '';
    branchCache = { branch: result, timestamp: now };
    return result;
  } catch (_err) {
    return '';
  }
}
