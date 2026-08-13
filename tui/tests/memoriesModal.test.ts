import { describe, expect, it } from 'vitest';
import {
  deriveMemoryTitle,
  filterMemories,
  formatMemoryTime,
  memoryPreview,
} from '../src/screens/Memory/MemoriesModal';
import type { MemoryEntry } from '../src/services/transport/WebSocketClient';

function entry(partial: Partial<MemoryEntry> & Pick<MemoryEntry, 'id' | 'scope' | 'content'>): MemoryEntry {
  return {
    title: undefined,
    source: undefined,
    tags: undefined,
    pinned: false,
    created_at: undefined,
    updated_at: undefined,
    size_chars: undefined,
    sessions: undefined,
    ...partial,
  };
}

const pinnedProject = entry({
  id: 'p1',
  scope: 'project',
  title: 'Stack',
  content: 'FastAPI + Ink.',
  tags: ['stack'],
  pinned: true,
  updated_at: '2026-07-01T00:00:00Z',
});

const olderSession = entry({
  id: 's1',
  scope: 'session',
  title: 'Plan pref',
  content: 'Write plans to disk.',
  updated_at: '2026-06-01T00:00:00Z',
});

const newerSession = entry({
  id: 's2',
  scope: 'session',
  title: 'Testing',
  content: 'Use vitest for the TUI.',
  updated_at: '2026-08-01T00:00:00Z',
});

describe('deriveMemoryTitle', () => {
  it('returns the title when present', () => {
    expect(deriveMemoryTitle(pinnedProject)).toBe('Stack');
  });

  it('falls back to a placeholder when title is missing or blank', () => {
    expect(deriveMemoryTitle(entry({ id: 'x', scope: 'project', content: 'body', title: '  ' }))).toBe(
      'Untitled memory',
    );
    expect(deriveMemoryTitle(entry({ id: 'y', scope: 'session', content: 'body' }))).toBe('Untitled memory');
  });
});

describe('memoryPreview', () => {
  it('returns short content unchanged', () => {
    expect(memoryPreview(olderSession, 50)).toBe('Write plans to disk.');
  });

  it('collapses whitespace before truncation', () => {
    const m = entry({ id: 'z', scope: 'project', content: 'a\n\n  b   c' });
    expect(memoryPreview(m, 10)).toBe('a b c');
  });

  it('truncates long content with an ellipsis', () => {
    const m = entry({
      id: 'w',
      scope: 'session',
      content: 'x'.repeat(500),
    });
    const preview = memoryPreview(m, 100);
    expect(preview.length).toBeLessThanOrEqual(100);
    expect(preview.endsWith('…')).toBe(true);
  });

  it('handles empty content', () => {
    expect(memoryPreview(entry({ id: 'v', scope: 'project', content: '' }), 10)).toBe('');
  });
});

describe('formatMemoryTime', () => {
  it('formats a valid ISO timestamp', () => {
    expect(formatMemoryTime('2026-08-01T00:00:00Z')).toMatch(/2026/i);
  });

  it('returns empty for missing or invalid values', () => {
    expect(formatMemoryTime(undefined)).toBe('');
    expect(formatMemoryTime('not-a-date')).toBe('');
  });
});

describe('filterMemories', () => {
  const all = [pinnedProject, olderSession, newerSession];

  it('keeps everything on the all scope', () => {
    expect(filterMemories(all, 'all', '')).toHaveLength(3);
  });

  it('filters by project scope', () => {
    const out = filterMemories(all, 'project', '');
    expect(out.map((m) => m.id)).toEqual(['p1']);
  });

  it('filters by session scope', () => {
    const out = filterMemories(all, 'session', '');
    expect(out.map((m) => m.id).sort()).toEqual(['s1', 's2']);
  });

  it('matches query across title, content, tags, and source', () => {
    const withSource = entry({
      id: 't1',
      scope: 'session',
      title: 'Whatever',
      content: 'noise',
      tags: ['theme'],
      source: 'abc.md',
    });
    const set = [pinnedProject, olderSession, newerSession, withSource];

    expect(filterMemories(set, 'all', 'stack').map((m) => m.id)).toEqual(['p1']);
    expect(filterMemories(set, 'all', 'vitest').map((m) => m.id)).toEqual(['s2']);
    expect(filterMemories(set, 'all', 'abc.md').map((m) => m.id)).toEqual(['t1']);
    expect(filterMemories(set, 'all', 'theme').map((m) => m.id)).toEqual(['t1']);
  });

  it('is case-insensitive', () => {
    expect(filterMemories(all, 'all', 'STACK').map((m) => m.id)).toEqual(['p1']);
  });

  it('sorts pinned first, then by updated_at descending', () => {
    const out = filterMemories(all, 'all', '');
    expect(out[0].id).toBe('p1');
    expect(out.map((m) => m.id).slice(1)).toEqual(['s2', 's1']);
  });

  it('sorts entries with missing dates last', () => {
    const undated = entry({ id: 'u1', scope: 'session', title: 'Undated', content: 'body' });
    const out = filterMemories([undated, newerSession], 'all', '');
    expect(out.map((m) => m.id)).toEqual(['s2', 'u1']);
  });

  it('returns an empty list when nothing matches the query', () => {
    expect(filterMemories(all, 'all', 'zzzz-not-found')).toEqual([]);
  });

  it('returns an empty list when the scope has no entries', () => {
    const out = filterMemories(all, 'session', 'stack');
    expect(out).toEqual([]);
  });

  it('does not mutate the input array', () => {
    const snapshot = all.map((m) => m.id);
    filterMemories(all, 'all', '');
    expect(all.map((m) => m.id)).toEqual(snapshot);
  });
});
