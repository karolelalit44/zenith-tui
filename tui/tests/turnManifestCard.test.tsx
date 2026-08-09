import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { formatTurnSummary, TurnManifestCard } from '../src/components/Display/Scenario/TurnManifestCard';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { TurnManifestEvent } from '../src/types/scenario';

function makeManifest(overrides: Partial<TurnManifestEvent> = {}): TurnManifestEvent {
  return {
    kind: 'turn_manifest',
    id: 'm1',
    created: [],
    modified: [],
    remaining: [],
    completed: true,
    stalled: false,
    files: [],
    ...overrides,
  };
}

function renderManifest(event: TurnManifestEvent) {
  return render(
    <ThemeProvider>
      <TurnManifestCard event={event} />
    </ThemeProvider>,
  );
}

describe('TurnManifestCard', () => {
  it('shows a completed turn with no changes', () => {
    const { lastFrame } = renderManifest(makeManifest());
    const frame = lastFrame();
    expect(frame).toContain('✓ Turn complete');
    expect(frame).toContain('no changes');
  });

  it('lists created files with their sizes', () => {
    const { lastFrame } = renderManifest(
      makeManifest({
        created: ['src/a.ts', 'src/b.ts'],
        files: [
          { path: 'src/a.ts', exists: true, size: 2048 },
          { path: 'src/b.ts', exists: true, size: 512 },
        ],
      }),
    );
    const frame = lastFrame();
    expect(frame).toContain('2 created');
    expect(frame).toContain('2 files');
    expect(frame).toContain('src/a.ts');
    expect(frame).toContain('2.0 KB');
    expect(frame).toContain('src/b.ts');
    expect(frame).toContain('512 B');
  });

  it('lists modified files separately even without size data (server only reports sizes for created files)', () => {
    const { lastFrame } = renderManifest(
      makeManifest({
        modified: ['README.md'],
      }),
    );
    const frame = lastFrame();
    expect(frame).toContain('1 modified');
    expect(frame).toContain('README.md');
  });

  it('renders created files with sizes alongside modified files without sizes', () => {
    const { lastFrame } = renderManifest(
      makeManifest({
        created: ['src/a.ts'],
        modified: ['README.md'],
        files: [{ path: 'src/a.ts', exists: true, size: 2048 }],
      }),
    );
    const frame = lastFrame();
    expect(frame).toContain('1 created');
    expect(frame).toContain('src/a.ts');
    expect(frame).toContain('2.0 KB');
    expect(frame).toContain('1 modified');
    expect(frame).toContain('README.md');
  });

  it('shows remaining steps when the turn is not complete', () => {
    const { lastFrame } = renderManifest(
      makeManifest({
        completed: false,
        stalled: false,
        remaining: ['Wire up the API client', 'Add tests'],
      }),
    );
    const frame = lastFrame();
    expect(frame).toContain('⧗ Turn paused');
    expect(frame).toContain('2 remaining');
    expect(frame).toContain('Remaining');
    expect(frame).toContain('Wire up the API client');
  });

  it('caps long file lists with an overflow line', () => {
    const created = Array.from({ length: 12 }, (_, i) => `src/f${i}.ts`);
    const files = created.map((path) => ({ path, exists: true, size: 10 }));
    const { lastFrame } = renderManifest(makeManifest({ created, files }));
    const frame = lastFrame();
    expect(frame).toContain('4 more');
  });

  it('marks a stalled turn distinctly', () => {
    const { lastFrame } = renderManifest(
      makeManifest({
        completed: false,
        stalled: true,
        remaining: ['stuck step'],
      }),
    );
    const frame = lastFrame();
    expect(frame).toContain('● Turn stalled');
  });
});

describe('formatTurnSummary', () => {
  it('summarizes created/modified counts and completion', () => {
    expect(formatTurnSummary(makeManifest({ created: ['a'], modified: ['b'], completed: true }))).toBe(
      '1 created · 1 modified · complete',
    );
  });

  it('reports remaining work when incomplete', () => {
    expect(formatTurnSummary(makeManifest({ completed: false, remaining: ['x', 'y'] }))).toBe('2 remaining');
  });

  it('returns a fallback when nothing changed', () => {
    expect(formatTurnSummary(makeManifest())).toBe('no changes');
  });
});
