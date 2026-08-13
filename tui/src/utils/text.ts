/** Collapsed preview length for long event messages (errors/warnings). */
export const MAX_MESSAGE_PREVIEW_LENGTH = 200;

/** Formats Zenith response time in 1-second increments (ignoring milliseconds).
 *
 * Rules:
 * - Whole-second intervals (< 60s): `2 s`, `3 s`, `33 s`
 * - Minute-based intervals (>= 60s): `1.2 minutes`, `37.40 minutes`
 * - Milliseconds are ignored completely. Updates only on 1-second interval changes.
 */
export function formatDuration(ms: number): string {
  const totalSec = Math.max(1, Math.floor(ms / 1000));
  if (totalSec < 60) {
    return `${totalSec} s`;
  }
  const mins = totalSec / 60;
  const formattedMins = mins % 1 === 0 ? mins.toFixed(1) : mins < 10 ? mins.toFixed(1) : mins.toFixed(2);
  return `${formattedMins} minutes`;
}

export function truncateEnd(text: string, maxLength: number): string {
  if (maxLength <= 0) return '';
  if (text.length <= maxLength) return text;
  if (maxLength === 1) return text.slice(0, 1);
  return `${text.slice(0, maxLength - 1)}…`;
}

export function truncateStart(text: string, maxLength: number): string {
  if (maxLength <= 0) return '';
  if (text.length <= maxLength) return text;
  if (maxLength === 1) return text.slice(-1);
  return `…${text.slice(text.length - (maxLength - 1))}`;
}

/** Formats a byte count as a compact human-readable string. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Flattens a markdown prompt to a single clean line (for banners/frames). */
export function sanitizeSingleLine(text: string): string {
  return text
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1') // markdown links -> their label
    .replace(/`{1,3}/g, '') // code fences / inline ticks
    .replace(/[*_>#]/g, '') // bold, italic, blockquote, heading markers
    .replace(/\s+/g, ' ') // collapse whitespace and newlines
    .trim();
}
