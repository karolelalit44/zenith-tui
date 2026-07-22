import { execSync } from 'node:child_process';

let branchCache: { branch: string; timestamp: number } | null = null;
const BRANCH_CACHE_TTL = 30000;

export function getActiveGitBranch(cwd: string = process.cwd()): string {
  const now = Date.now();
  if (branchCache && now - branchCache.timestamp < BRANCH_CACHE_TTL) {
    return branchCache.branch;
  }
  try {
    const branch = execSync('git branch --show-current', { cwd, encoding: 'utf-8', timeout: 1000 });
    const trimmed = branch.trim();
    const result = trimmed || 'main';
    branchCache = { branch: result, timestamp: now };
    return result;
  } catch (_err) {
    return 'main';
  }
}
