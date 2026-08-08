import { describe, expect, it } from 'vitest';
import { sanitizeSingleLine, truncateEnd } from '../src/utils/text';

describe('sanitizeSingleLine — banner-safe prompt flattening', () => {
  it('strips markdown headings, ticks and emphasis', () => {
    const input = '### Build a complete FastAPI application named `library-mgmnt-sys`.';
    const out = sanitizeSingleLine(input);
    expect(out).not.toContain('#');
    expect(out).not.toContain('`');
    expect(out).toBe('Build a complete FastAPI application named library-mgmnt-sys.');
  });

  it('collapses newlines and whitespace to a single line', () => {
    const out = sanitizeSingleLine('1. **CRUD APIs**\n   * Create a book\n\n   * Delete a book');
    expect(out).not.toContain('\n');
    expect(out).not.toMatch(/\s{2,}/);
    expect(out).toContain('CRUD APIs');
  });

  it('reduces markdown links to their label', () => {
    const out = sanitizeSingleLine('see [the docs](https://example.com) for details');
    expect(out).toBe('see the docs for details');
  });
});

describe('truncateEnd', () => {
  it('leaves short text unchanged', () => {
    expect(truncateEnd('hi', 5)).toBe('hi');
  });

  it('truncates long text with an ellipsis', () => {
    expect(truncateEnd('0123456789', 5)).toBe('0123…');
  });
});
