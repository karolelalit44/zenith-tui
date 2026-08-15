import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ENV_FILE_PATHS = (() => {
  const __dirname = dirname(fileURLToPath(import.meta.url));
  return [
    resolve(__dirname, '../../.env'),
    resolve(__dirname, '../../../.env'),
    resolve(__dirname, '../../.env.example'),
  ];
})();

/** Parse the first existing env file (`.env`, repo-root `.env`, then `.env.example`). */
export function readDotEnv(): Record<string, string> {
  const vars: Record<string, string> = {};
  for (const p of ENV_FILE_PATHS) {
    if (!existsSync(p)) continue;
    for (const line of readFileSync(p, 'utf-8').split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eqIdx = trimmed.indexOf('=');
      if (eqIdx < 1) continue;
      vars[trimmed.slice(0, eqIdx).trim()] = trimmed.slice(eqIdx + 1).trim();
    }
    break;
  }
  return vars;
}

function loadDotEnv(): void {
  const vars = readDotEnv();
  for (const [key, val] of Object.entries(vars)) {
    if (!process.env[key]) process.env[key] = val;
  }
}

loadDotEnv();

export function envStr(key: string): string {
  const val = process.env[key];
  if (val === undefined || val.trim() === '') {
    throw new Error(`Required environment variable '${key}' is not set. Set it in tui/.env (see tui/.env.example).`);
  }
  return val.trim();
}

export function envInt(key: string): number {
  const n = Number(envStr(key));
  if (Number.isNaN(n)) {
    throw new Error(`Environment variable '${key}' must be a number, got: ${JSON.stringify(envStr(key))}`);
  }
  return n;
}

export function envFloat(key: string): number {
  const n = Number.parseFloat(envStr(key));
  if (Number.isNaN(n)) {
    throw new Error(`Environment variable '${key}' must be a number, got: ${JSON.stringify(envStr(key))}`);
  }
  return n;
}
