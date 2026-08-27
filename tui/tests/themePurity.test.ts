import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { themeOptions, themes } from '../src/theme/theme';

const SRC_DIR = join(__dirname, '..', 'src');
const HEX_COLOR_RE = /#[0-9A-Fa-f]{6}\b/g;

function collectTsFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      out.push(...collectTsFiles(full));
    } else if (/\.(ts|tsx)$/.test(name)) {
      out.push(full);
    }
  }
  return out;
}

describe('theme purity — colors live only in themes.json', () => {
  it('contains no hardcoded hex colors outside src/theme/', () => {
    const offenders: string[] = [];
    for (const file of collectTsFiles(SRC_DIR)) {
      if (file.replace(/\\/g, '/').includes('/src/theme/')) continue;
      const content = readFileSync(file, 'utf8');
      for (const match of content.matchAll(HEX_COLOR_RE)) {
        offenders.push(`${file}: ${match[0]}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe('themes.json integrity', () => {
  it('exposes a palette for every theme option and vice versa', () => {
    expect(themeOptions.length).toBeGreaterThan(0);
    for (const option of themeOptions) {
      expect(themes[option.id]).toBeDefined();
    }
  });

  it('defines every semantic token for every theme', () => {
    for (const [id, theme] of Object.entries(themes)) {
      const { bg, border, text, status, diff, code, shadow, decorative, logo } = theme.colors;
      for (const group of [bg, border, text, status, diff, code, shadow]) {
        for (const [key, value] of Object.entries(group)) {
          expect(value, `${id}.colors.${key}`).toMatch(/^#[0-9A-Fa-f]{6}$/);
        }
      }
      for (const value of Object.values(decorative.trafficLight)) {
        expect(value, `${id}.decorative.trafficLight`).toMatch(/^#[0-9A-Fa-f]{6}$/);
      }
      for (const value of logo) {
        expect(value, `${id}.logo`).toMatch(/^#[0-9A-Fa-f]{6}$/);
      }
    }
  });

  it('keeps status colors mutually distinct within each theme', () => {
    for (const [id, theme] of Object.entries(themes)) {
      const values = Object.values(theme.colors.status);
      expect(new Set(values).size, `${id}.status must not repeat a color across roles`).toBe(values.length);
    }
  });

  it('keeps text.error visually distinct from body/muted text', () => {
    for (const [id, theme] of Object.entries(themes)) {
      expect(theme.colors.text.error.toLowerCase(), `${id}.text.error`).not.toBe(theme.colors.text.muted.toLowerCase());
    }
  });

  it('derives theme options with names and four-swatch previews', () => {
    for (const option of themeOptions) {
      expect(option.name).not.toBe(option.id);
      expect(option.swatch).toHaveLength(4);
    }
  });
});
