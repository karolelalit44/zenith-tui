import { highlight, supportsLanguage } from 'cli-highlight';
import type { Theme } from '../theme/theme';

/**
 * A source-code syntax segment with an already-resolved ink color.
 *
 * Rendered "flat" (color resolved here) so callers only need a plain `Text`
 * node per segment. This keeps the highlighting purely theme-driven: the model
 * of ink colors is derived from the active `Theme`, never hardcoded.
 */
export interface SyntaxSegment {
  text: string;
  color: string;
}

/**
 * ANSI SGR escape sequence: `<ESC>[<params>m`. Parameters are `;`-separated
 * decimal codes. This regex is the only thing we match against; everything the
 * underlying highlighter emits that we do not recognize is ignored and the
 * current color is carried forward (never breaks rendering).
 */
const ANSI_ESCAPE_RE = /\x1b\[([0-9;]*)m/g;

/**
 * Map a basic ANSI SGR foreground color code to a semantic theme token.
 *
 * SGR base colors (30-37) and bright variants (90-97) are an external protocol
 * standard (ECMA-48 / ISO 6429) — the only strings we are permitted to hold
 * literally. The *choice of what each code means visually* is delegated to the
 * active theme (not hardcoded), so every supported language/theme maps cleanly
 * without the UI ever embedding a concrete color value.
 */
function resolveFgColor(code: number, theme: Theme): string {
  const bright = code >= 90 ? code - 60 : code;
  switch (bright) {
    case 30:
      return theme.colors.text.dim;
    case 31:
      return theme.colors.status.error;
    case 32:
      return theme.colors.status.success;
    case 33:
      return theme.colors.status.warning;
    case 34:
      return theme.colors.status.info;
    case 35:
      return theme.colors.status.accent;
    case 36:
      return theme.colors.status.info;
    case 37:
      return theme.colors.text.bright;
    default:
      return theme.colors.text.ethereal;
  }
}

/**
 * Highlight `source` into a flat list of colored segments using the active
 * theme. `language` is optional; when omitted the underlying highlighter
 * attempts auto-detection. Never throws on unknown input: if highlighting
 * fails, the whole source is returned as a single plain segment.
 */
export function highlightCode(source: string, theme: Theme, language?: string): SyntaxSegment[] {
  let ansi: string;
  try {
    const validLang = language && supportsLanguage(language) ? language : undefined;
    ansi = validLang ? highlight(source, { language: validLang }) : highlight(source);
  } catch {
    return source ? [{ text: source, color: theme.colors.text.ethereal }] : [];
  }
  if (!ansi) return [];

  const segments: SyntaxSegment[] = [];
  let color = theme.colors.text.ethereal;
  let lastIndex = 0;

  for (const match of ansi.matchAll(ANSI_ESCAPE_RE)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      segments.push({ text: ansi.slice(lastIndex, index), color });
    }
    const codes = match[1] ? match[1].split(';').map((c) => Number.parseInt(c, 10)) : [0];
    for (const code of codes) {
      if (code === 0) {
        color = theme.colors.text.ethereal; // reset
      } else if (code === 1) {
        color = theme.colors.text.bright; // bold → bright
      } else if (code >= 30 && code <= 37) {
        color = resolveFgColor(code, theme);
      } else if (code >= 90 && code <= 97) {
        color = resolveFgColor(code, theme);
      }
    }
    lastIndex = index + match[0].length;
  }
  if (lastIndex < ansi.length) {
    segments.push({ text: ansi.slice(lastIndex), color });
  }
  return segments;
}
