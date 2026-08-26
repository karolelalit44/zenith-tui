/**
 * Compact one-line error summary for tool failures.
 *
 * Raw OS/CLI errors are multi-line walls ("'X' is not recognized...\n"
 * "operable program or batch file.") that splattered across frames and
 * read like status text. Show the first meaningful line plus a "+N more
 * lines" hint — the full stderr still reaches the model via the tool
 * result, this is purely presentation.
 */
export function formatErrorSummary(error: string, maxFirstLine = 120): string {
  const lines = (error ?? '')
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length === 0) return '';
  let first = lines[0];
  if (first.length > maxFirstLine) first = `${first.slice(0, maxFirstLine - 1)}…`;
  const rest = lines.length - 1;
  return rest > 0 ? `✗ ${first} (+${rest} more lines)` : `✗ ${first}`;
}
