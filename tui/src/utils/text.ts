export function truncateEnd(text: string, maxLength: number): string {
  if (maxLength <= 0) return '';
  if (text.length <= maxLength) return text;
  if (maxLength === 1) return text.slice(0, 1);
  return `${text.slice(0, maxLength - 1)}…`;
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
