/** Collapsed preview length for long event messages (errors/warnings). */
export const MAX_MESSAGE_PREVIEW_LENGTH = 200;

/** Formats a duration in milliseconds into a compact human string.
 *
 * Rules:
 * - Whole-second intervals (< 60s): `2 s`, `3 s`, `33 s`
 *   Sub-second inputs floor to `1 s` so instant calls never read as zero.
 * - Minute-based intervals (>= 60s): `1.2 minutes`, `37.40 minutes`
 * - zero/negative input renders nothing (`''`) so instant calls don't
 *   fake a duration reading.
 */
export function formatDuration(ms: number): string {
  if (ms <= 0) return '';
  const totalMs = Math.max(1, Math.round(ms));
  const totalSec = totalMs / 1000;
  if (totalSec < 60) {
    return `${Math.max(1, Math.floor(totalSec))} s`;
  }
  const mins = totalSec / 60;
  const formattedMins = mins % 1 === 0 ? mins.toFixed(1) : mins < 10 ? mins.toFixed(1) : mins.toFixed(2);
  return `${formattedMins} minutes`;
}

/** Truncates from the middle, keeping both ends readable (e.g. long model ids). */
export function truncateMiddle(text: string, maxLength: number): string {
  if (maxLength <= 0) return '';
  if (text.length <= maxLength) return text;
  if (maxLength <= 3) return '…';
  const half = Math.floor((maxLength - 1) / 2);
  const tailHalf = maxLength - 1 - half;
  return `${text.slice(0, half)}…${text.slice(-tailHalf)}`;
}

/** Words whose English plural is not just `noun + s`. */
const IRREGULAR_PLURALS: Record<string, string> = {
  match: 'matches',
};

/** Singular/plural count phrase: `1 line`, `3 lines`, `1 match`, `5 matches`. */
export function countWord(count: number, noun: string): string {
  if (count === 1) return `1 ${noun}`;
  return `${count} ${IRREGULAR_PLURALS[noun] ?? `${noun}s`}`;
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
