import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

function loadDotEnv(): void {
  const __dirname = dirname(fileURLToPath(import.meta.url));
  const candidates = [resolve(__dirname, '../../.env'), resolve(__dirname, '../../../.env')];
  for (const p of candidates) {
    if (existsSync(p)) {
      const content = readFileSync(p, 'utf-8');
      for (const line of content.split('\n')) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;
        const eqIdx = trimmed.indexOf('=');
        if (eqIdx < 1) continue;
        const key = trimmed.slice(0, eqIdx).trim();
        const val = trimmed.slice(eqIdx + 1).trim();
        if (!process.env[key]) {
          process.env[key] = val;
        }
      }
      return;
    }
  }
}

loadDotEnv();

export function requireEnv(key: string): string {
  const val = process.env?.[key];
  if (val === undefined || val.trim() === '') {
    throw new Error(`Required environment variable '${key}' is not set. Set it before starting the app.`);
  }
  return val.trim();
}

export function requireInt(key: string): number {
  const raw = requireEnv(key);
  const n = Number(raw);
  if (Number.isNaN(n)) {
    throw new Error(`Environment variable '${key}' must be a number, got: ${JSON.stringify(raw)}`);
  }
  return n;
}

export function requireFloat(key: string): number {
  const raw = requireEnv(key);
  const n = parseFloat(raw);
  if (Number.isNaN(n)) {
    throw new Error(`Environment variable '${key}' must be a float, got: ${JSON.stringify(raw)}`);
  }
  return n;
}

export function envInt(key: string, fallback: number): number {
  const raw = process.env?.[key];
  if (raw === undefined || raw.trim() === '') return fallback;
  const n = Number(raw.trim());
  if (Number.isNaN(n)) return fallback;
  return n;
}
