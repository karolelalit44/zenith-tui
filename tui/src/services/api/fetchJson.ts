const BACKEND_BASE = process.env.ZENITH_BACKEND_URL || process.env.VITE_BACKEND_URL || 'http://localhost:8765';

function backendUrl(path: string): string {
  return `${BACKEND_BASE.replace(/\/+$/, '')}${path}`;
}

export async function fetchJson<T>(path: string, options?: RequestInit & { timeout?: number }): Promise<T> {
  const { timeout, ...fetchOptions } = options || {};
  const signal = timeout ? AbortSignal.timeout(timeout) : undefined;
  const res = await fetch(backendUrl(path), {
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    signal,
    ...fetchOptions,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Backend error ${res.status}: ${text || res.statusText}`);
  }
  return res.json() as Promise<T>;
}
