import { execSync } from 'node:child_process';
import { requireInt } from '../config/env';

let branchCache: { branch: string; timestamp: number } | null = null;
const BRANCH_CACHE_TTL = requireInt('ZENITH_GIT_CACHE_TTL');
const GIT_TIMEOUT = requireInt('ZENITH_GIT_TIMEOUT');

export function getActiveGitBranch(cwd: string = process.cwd()): string {
  const now = Date.now();
  if (branchCache && now - branchCache.timestamp < BRANCH_CACHE_TTL) {
    return branchCache.branch;
  }
  try {
    const branch = execSync('git branch --show-current', {
      cwd,
      encoding: 'utf-8',
      timeout: GIT_TIMEOUT,
    });
    const trimmed = branch.trim();
    const result = trimmed || 'main';
    branchCache = { branch: result, timestamp: now };
    return result;
  } catch (_err) {
    return 'main';
  }
}
