import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { FileDiffBlock, parseDiffOrContent } from '../src/components/Display/Scenario/FileDiffBlock';
import { ThemeProvider } from '../src/theme/ThemeContext';

function stripAnsi(s: string): string {
  // eslint-disable-next-line no-control-regex
  return s.replace(/\u001b\[[0-9;]*m/g, '');
}

function renderDiff(diffOrContent: string, title?: string) {
  const { lastFrame } = render(
    <ThemeProvider>
      <FileDiffBlock diffOrContent={diffOrContent} title={title} />
    </ThemeProvider>,
  );
  return lastFrame();
}

describe('parseDiffOrContent', () => {
  it('treats raw content as a brand-new file (all additions)', () => {
    const lines = parseDiffOrContent('alpha\nbeta\n');
    expect(lines.map((l) => l.type)).toEqual(['add', 'add']);
    expect(lines[0].newLineNumber).toBe(1);
    expect(lines[1].newLineNumber).toBe(2);
  });

  it('parses a unified diff into hunk, delete, add and context lines', () => {
    const lines = parseDiffOrContent('@@ -1,2 +1,2 @@\n-old\n+new\n context\n');
    expect(lines.map((l) => l.type)).toEqual(['hunk', 'delete', 'add', 'normal']);
    expect(lines[1].oldLineNumber).toBe(1);
    expect(lines[2].newLineNumber).toBe(1);
  });
});

describe('FileDiffBlock', () => {
  it('renders a brand-new file with the +lines badge and content, without word-level hot-spot fills', () => {
    const frame = renderDiff('line one\nline two\nline three', 'src/foo.ts');
    const clean = stripAnsi(frame);
    expect(clean).toContain('src/foo.ts');
    expect(clean).toContain('+3 lines');
    expect(clean).toContain('line one');
    expect(clean).toContain('line two');
    expect(clean).toContain('line three');
  });

  it('renders a unified diff hunk in a scope frame with the +/- badge inline', () => {
    const diff = '@@ -1,3 +1,3 @@\n-old alpha\n+new alpha\n same\n';
    const frame = renderDiff(diff, 'src/bar.ts');
    const clean = stripAnsi(frame);
    expect(clean).toContain('@@ -1,3 +1,3 @@');
    expect(clean).toContain('+1 -1 lines');
    expect(clean).toContain('old alpha');
    expect(clean).toContain('new alpha');
    expect(clean).toContain('same');
  });

  it('shows only the deletion side when a line is removed without a replacement', () => {
    const frame = renderDiff('@@ -1 +1 @@\n-only\n', 'src/drop.ts');
    const clean = stripAnsi(frame);
    expect(clean).toContain('-1 lines');
    expect(clean).toContain('only');
  });

  it('returns nothing for empty input', () => {
    const { lastFrame } = render(
      <ThemeProvider>
        <FileDiffBlock diffOrContent="" />
      </ThemeProvider>,
    );
    expect(lastFrame()).toBe('');
  });
});
