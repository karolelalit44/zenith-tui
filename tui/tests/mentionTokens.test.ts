import { describe, expect, it } from 'vitest';
import {
  activeMentionAtOffset,
  insertMentionAt,
  parseMentions,
  parseStyledSegments,
  removeMention,
  replaceMention,
  tokenAtOffset,
} from '../src/utils/mentionTokens';

describe('parseMentions', () => {
  it('finds a single mention at the start', () => {
    expect(parseMentions('@src/auth')).toEqual([{ raw: '@src/auth', text: 'src/auth', start: 0, end: 9 }]);
  });

  it('finds mid-text mentions and preserves other text', () => {
    expect(parseMentions('fix @login.ts now')).toEqual([{ raw: '@login.ts', text: 'login.ts', start: 4, end: 13 }]);
  });

  it('handles a trailing empty @', () => {
    expect(parseMentions('hello @')).toEqual([{ raw: '@', text: '', start: 6, end: 7 }]);
  });

  it('finds multiple mentions', () => {
    const tokens = parseMentions('@a @b/c');
    expect(tokens.map((t) => t.raw)).toEqual(['@a', '@b/c']);
  });

  it('stops mentions at whitespace', () => {
    const tokens = parseMentions('@foo bar');
    expect(tokens[0].text).toBe('foo');
  });
});

describe('activeMentionAtOffset', () => {
  it('returns the token when the cursor sits right after an "@"', () => {
    const t = activeMentionAtOffset('@', 1);
    expect(t?.text).toBe('');
  });

  it('returns the token while typing inside it', () => {
    const t = activeMentionAtOffset('fix @log', 8);
    expect(t?.raw).toBe('@log');
  });

  it('returns undefined when no "@" is active near the cursor', () => {
    expect(activeMentionAtOffset('fix the bug', 5)).toBeUndefined();
  });

  it('does not trigger on "@" before the cursor with a space after', () => {
    // Cursor after '@' + space => not an active token.
    expect(activeMentionAtOffset('@ ', 2)).toBeUndefined();
  });
});

describe('replaceMention', () => {
  it('replaces only the token, preserving surrounding text', () => {
    const tokens = parseMentions('fix @log now');
    const { value, end } = replaceMention('fix @log now', tokens[0], 'src/login.ts');
    expect(value).toBe('fix @src/login.ts now');
    expect(parseMentions(value)[0].text).toBe('src/login.ts');
    expect(end).toBe('fix @'.length + 'src/login.ts'.length);
  });
});

describe('insertMentionAt and removeMention', () => {
  it('inserts a mention at a position', () => {
    const { value, end } = insertMentionAt('fix  now', 4, 'a.ts');
    expect(value).toBe('fix @a.ts now');
    expect(end).toBe(9);
  });

  it('removes a mention token', () => {
    const tokens = parseMentions('fix @a.ts now');
    const { value } = removeMention('fix @a.ts now', tokens[0]);
    expect(value).toBe('fix  now');
  });
});

describe('tokenAtOffset', () => {
  it('finds the token containing a position', () => {
    const t = tokenAtOffset('fix @a.ts now', 6);
    expect(t?.raw).toBe('@a.ts');
  });
});

describe('parseStyledSegments', () => {
  it('parses plain text without mentions', () => {
    expect(parseStyledSegments('hello world')).toEqual([{ type: 'text', text: 'hello world' }]);
  });

  it('parses mentions and surrounding text', () => {
    expect(parseStyledSegments('@todo.md how many task')).toEqual([
      { type: 'mention', text: '@todo.md' },
      { type: 'text', text: ' how many task' },
    ]);
  });

  it('parses multiple mentions and paste tokens', () => {
    expect(parseStyledSegments('check @a.ts and [Pasted +5 lines #1] then @b.ts')).toEqual([
      { type: 'text', text: 'check ' },
      { type: 'mention', text: '@a.ts' },
      { type: 'text', text: ' and ' },
      { type: 'paste', text: '[Pasted +5 lines #1]', pasteInfo: '+5 lines' },
      { type: 'text', text: ' then ' },
      { type: 'mention', text: '@b.ts' },
    ]);
  });

  it('treats a solitary @ as plain text', () => {
    expect(parseStyledSegments('contact @ me')).toEqual([{ type: 'text', text: 'contact @ me' }]);
  });
});
