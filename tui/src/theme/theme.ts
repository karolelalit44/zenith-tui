import themesJson from './themes.json';
import type { Theme } from './types';

export type { Theme };

/**
 * Single source of truth for every theme palette is `themes.json`; this module
 * only types it and derives UI-facing helpers. Never add color literals here.
 */
const typedThemes = themesJson as unknown as Record<string, Theme>;

/** Fail loudly at startup if a palette in themes.json drifts from the Theme shape. */
function assertThemeShape(id: string, t: Theme): void {
  const groups: unknown[] = [
    t.colors.bg,
    t.colors.border,
    t.colors.text,
    t.colors.status,
    t.colors.diff,
    t.colors.code,
    t.colors.shadow,
    t.colors.decorative?.trafficLight,
  ];
  const complete =
    groups.every(
      (g) => !!g && Object.values(g as Record<string, unknown>).every((v) => typeof v === 'string' && v.length > 0),
    ) &&
    Array.isArray(t.colors.logo) &&
    t.colors.logo.length > 0;
  if (!complete) {
    throw new Error(`themes.json: palette "${id}" does not match the Theme shape`);
  }
}

export const themes: Record<string, Theme> = (() => {
  for (const [id, theme] of Object.entries(typedThemes)) {
    assertThemeShape(id, theme);
  }
  return typedThemes;
})();

export interface ThemeOption {
  id: string;
  name: string;
  swatch: string[];
}

function themeDisplayName(id: string): string {
  return id
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

/** Theme picker entries derived from the themes registry — never duplicated. */
export const themeOptions: ThemeOption[] = Object.entries(themes).map(([id, theme]) => ({
  id,
  name: themeDisplayName(id),
  swatch: theme.colors.logo.slice(0, 4),
}));
