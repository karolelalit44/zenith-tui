/** Collapsed preview length for long event messages (errors/warnings). */
export const MAX_MESSAGE_PREVIEW_LENGTH = 200;

/** Formats an elapsed duration (ms) as a compact human-readable string. */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const totalSec = ms / 1000;
  if (totalSec < 60) return `${totalSec.toFixed(1)}s`;
  const mins = Math.floor(totalSec / 60);
  const secs = Math.round(totalSec % 60);
  if (mins < 60) return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
  const hrs = Math.floor(mins / 60);
  const remMins = mins % 60;
  return remMins > 0 ? `${hrs}h ${remMins}m` : `${hrs}h`;
}

export function truncateEnd(text: string, maxLength: number): string {
  if (maxLength <= 0) return '';
  if (text.length <= maxLength) return text;
  if (maxLength === 1) return text.slice(0, 1);
  return `${text.slice(0, maxLength - 1)}…`;
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
