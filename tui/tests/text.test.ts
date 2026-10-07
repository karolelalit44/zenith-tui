import { describe, expect, it } from 'vitest';
import { isDegenerateMessage, sanitizeSingleLine, truncateEnd } from '../src/utils/text';

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

describe('isDegenerateMessage', () => {
  it('returns true for empty or whitespace messages', () => {
    expect(isDegenerateMessage('')).toBe(true);
    expect(isDegenerateMessage('   ')).toBe(true);
    expect(isDegenerateMessage(null)).toBe(true);
    expect(isDegenerateMessage(undefined)).toBe(true);
  });

  it('returns true for degenerate placeholder tokens', () => {
    expect(isDegenerateMessage('[empty assistant turn]')).toBe(true);
    expect(isDegenerateMessage('empty assistant turn')).toBe(true);
    expect(isDegenerateMessage('[tool calls]')).toBe(true);
    expect(isDegenerateMessage('[thinking]')).toBe(true);
    expect(isDegenerateMessage('  [empty assistant turn]  ')).toBe(true);
    expect(isDegenerateMessage('"[empty assistant turn]"')).toBe(true);
  });

  it('returns false for real assistant answers and normal short words', () => {
    expect(isDegenerateMessage('Done.')).toBe(false);
    expect(isDegenerateMessage('done')).toBe(false);
    expect(isDegenerateMessage('Here is the report you requested.')).toBe(false);
  });
});

