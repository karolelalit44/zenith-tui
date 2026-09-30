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
    const { lines } = parseDiffOrContent('alpha\nbeta\n');
    expect(lines.map((l) => l.type)).toEqual(['add', 'add']);
    expect(lines[0].newLineNumber).toBe(1);
    expect(lines[1].newLineNumber).toBe(2);
  });

  it('drops the hunk header but keeps line numbering resynced to it', () => {
    // The "@@ -1,2 +1,2 @@" row is display noise: the gutter and the coloured
    // rows already carry the position. What matters is that the numbers after
    // it restart at the hunk's declared start.
    const { lines } = parseDiffOrContent('@@ -1,2 +1,2 @@\n-old\n+new\n context\n');
    expect(lines.map((l) => l.type)).toEqual(['delete', 'add', 'normal']);
    expect(lines[0].oldLineNumber).toBe(1);
    expect(lines[1].newLineNumber).toBe(1);
  });

  it('emits a section marker per file so a multi-file patch stays legible', () => {
    // Without per-file markers, a three-file apply_patch rendered as one
    // anonymous block and the user could not tell where one file ended.
    const patch = [
      'diff --git a/a.ts b/a.ts',
      '--- a/a.ts',
      '+++ b/a.ts',
      '@@ -1 +1 @@',
      '-one',
      '+ONE',
      'diff --git a/b.ts b/b.ts',
      '--- a/b.ts',
      '+++ b/b.ts',
      '@@ -1 +1 @@',
      '-two',
      '+TWO',
    ].join('\n');
    const { lines } = parseDiffOrContent(patch);
    const files = lines.filter((l) => l.type === 'file').map((l) => l.content);
    expect(files).toEqual(['a.ts', 'b.ts']);
    expect(lines.filter((l) => l.type === 'add').map((l) => l.content)).toEqual(['ONE', 'TWO']);
  });

  it('reports how many lines the cap hid instead of dropping them silently', () => {
    const body = Array.from({ length: 50 }, (_, i) => `+line ${i}`).join('\n');
    const { lines, truncated } = parseDiffOrContent(`@@ -1 +1 @@\n${body}`, 10);
    expect(truncated).toBeGreaterThan(0);
    expect(lines.length).toBe(10);
    // An uncapped parse hides nothing, which is what makes ctrl+E a real answer.
    expect(parseDiffOrContent(`@@ -1 +1 @@\n${body}`, Number.POSITIVE_INFINITY).truncated).toBe(0);
  });
});

describe('FileDiffBlock', () => {
  it('renders a brand-new file as numbered green addition rows with the content', () => {
    const frame = renderDiff('line one\nline two\nline three', 'src/foo.ts');
    const clean = stripAnsi(frame);
    expect(clean).toContain('1 |');
    expect(clean).toContain('line one');
    expect(clean).toContain('line two');
    expect(clean).toContain('line three');
  });

  it('renders a unified diff hunk with delete, add and context lines', () => {
    const diff = '@@ -1,3 +1,3 @@\n-old alpha\n+new alpha\n same\n';
    const frame = renderDiff(diff, 'src/bar.ts');
    const clean = stripAnsi(frame);
    // Hunk headers (@@ … @@) are deliberately hidden in the rendered output;
    // only the colored delete/add/context lines and gutters are shown.
    expect(clean).not.toContain('@@');
    expect(clean).toContain('old alpha');
    expect(clean).toContain('new alpha');
    expect(clean).toContain('same');
  });

  it('shows only the deletion side when a line is removed without a replacement', () => {
    const frame = renderDiff('@@ -1 +1 @@\n-only\n', 'src/drop.ts');
    const clean = stripAnsi(frame);
    expect(clean).not.toContain('@@');
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
