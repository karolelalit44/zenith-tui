import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { TerminalMarkdown } from '../src/components/Display/Scenario/TerminalMarkdown';
import { ThemeProvider } from '../src/theme/ThemeContext';
import { renderAtWidth } from './helpers/terminalStubs';

function stripAnsi(s: string): string {
  // eslint-disable-next-line no-control-regex
  return s.replace(/\u001b\[[0-9;]*m/g, '');
}

function renderMarkdown(content: string, columns?: number) {
  const node = (
    <ThemeProvider>
      <TerminalMarkdown content={content} />
    </ThemeProvider>
  );
  const lastFrame = columns ? renderAtWidth(node, { columns }).lastFrame : render(node).lastFrame;
  return stripAnsi(lastFrame());
}

describe('TerminalMarkdown inline code spacing', () => {
  it('does not add padding spaces inside inline code spans', () => {
    const frame = renderMarkdown('The `rgmb-hub` FastAPI project uses `uvicorn`.');
    expect(frame).not.toMatch(/[^\s]\s{2,}/);
    expect(frame).toContain('The rgmb-hub FastAPI project uses uvicorn.');
  });

  it('keeps single natural spaces between code and surrounding words', () => {
    const frame = renderMarkdown('Create `Dockerfile` & `docker-compose.yml` for the service.');
    expect(frame).toContain('Create Dockerfile & docker-compose.yml for the service.');
    expect(frame).not.toMatch(/[^\s]\s{2,}/);
  });

  it('does not insert padding spaces around code adjacent to punctuation', () => {
    const frame = renderMarkdown('Hit (`/health`) then call (`POST /items`).');
    expect(frame).toContain('Hit (/health) then call (POST /items).');
    expect(frame).not.toContain(' /health ');
    expect(frame).not.toContain(' /items ');
  });
});

describe('TerminalMarkdown streaming windowing and scrolling', () => {
  const multiLineContent = Array.from({ length: 20 }, (_, i) => `Line ${i + 1}`).join('\n');

  it('renders all lines when isRunning is false even if maxLines is set', () => {
    const { lastFrame } = render(
      <ThemeProvider>
        <TerminalMarkdown content={multiLineContent} isRunning={false} maxLines={5} />
      </ThemeProvider>,
    );
    const frame = stripAnsi(lastFrame());
    expect(frame).toContain('Line 1');
    expect(frame).toContain('Line 20');
  });

  it('windows to the bottom lines when isRunning is true and not user-scrolled', () => {
    const { lastFrame } = render(
      <ThemeProvider>
        <TerminalMarkdown content={multiLineContent} isRunning={true} maxLines={5} />
      </ThemeProvider>,
    );
    const frame = stripAnsi(lastFrame());
    expect(frame).not.toContain('Line 1\n');
    expect(frame).toContain('Line 16');
    expect(frame).toContain('Line 20');
    expect(frame).toContain('earlier lines');
  });

  it('windows to the scrolled offset when user scrolls up', () => {
    const { lastFrame } = render(
      <ThemeProvider>
        <TerminalMarkdown content={multiLineContent} isRunning={true} maxLines={5} scrollOffset={0} />
      </ThemeProvider>,
    );
    const frame = stripAnsi(lastFrame());
    expect(frame).toContain('Line 1');
    expect(frame).toContain('Line 5');
    expect(frame).not.toContain('Line 20');
    expect(frame).toContain('lines below');
  });
});

describe('TerminalMarkdown table rendering and line wrapping', () => {
  it('renders markdown table with borders and headers', () => {
    const tableMd = `
| Step | Action |
| --- | --- |
| 1 | Init |
| 2 | Build |
`.trim();
    const frame = renderMarkdown(tableMd);
    expect(frame).toContain('┌');
    expect(frame).toContain('┐');
    expect(frame).toContain('Step');
    expect(frame).toContain('Action');
    expect(frame).toContain('Init');
    expect(frame).toContain('Build');
    expect(frame).toContain('└');
    expect(frame).toContain('┘');
  });

  it('renders answer tables as compact summary rows instead of bordered grids', () => {
    const tableMd = `
| Item | Detail |
| --- | --- |
| Latest stable major version | **Vite 8.1** |
| Source URL | <https://vite.dev/blog/announcing-vite8-1> |
`.trim();
    const frame = renderMarkdown(tableMd);
    expect(frame).not.toContain('┌');
    expect(frame).not.toContain('│');
    expect(frame).toContain('Latest stable major version');
    expect(frame).toContain('Vite 8.1');
    expect(frame).toContain('Source URL');
  });

  it('renders task status tables as compact checklist rows', () => {
    const tableMd = `
| Task | Status |
| --- | --- |
| t1: Search official docs | ✅ |
| t2: Record source URL | ✅ |
`.trim();
    const frame = renderMarkdown(tableMd);
    expect(frame).not.toContain('┌');
    expect(frame).toContain('✓');
    expect(frame).toContain('t1: Search official docs');
    expect(frame).toContain('t2: Record source URL');
  });

  it('wraps long cell content across multiple lines without truncating with ellipsis', () => {
    const tableMd = `
| Key | Description |
| --- | --- |
| auth | User authentication flow using JWT tokens and refresh token rotation |
`.trim();
    const frame = renderMarkdown(tableMd);
    // Previously truncateEnd would insert '…' and cut off the description.
    expect(frame).not.toContain('…');
    // Words should be present across wrapped lines.
    expect(frame).toContain('User authentication flow');
    expect(frame).toContain('refresh token');
    expect(frame).toContain('rotation');
    // Lines of the same row should have borders
    const lines = frame.split('\n').filter((l) => l.includes('│'));
    // Should have header line + at least 2 content lines for the wrapped cell
    expect(lines.length).toBeGreaterThanOrEqual(3);
  });

  it('wraps cells containing <br> tags across lines', () => {
    const tableMd = `
| ID | Items |
| --- | --- |
| 1 | Item Alpha<br>Item Beta<br>Item Gamma |
`.trim();
    const frame = renderMarkdown(tableMd);
    expect(frame).toContain('Item Alpha');
    expect(frame).toContain('Item Beta');
    expect(frame).toContain('Item Gamma');
    expect(frame).not.toContain('<br>');
  });

  it('keeps borders for a two-column table that is NOT a checklist', () => {
    // The compact form is keyed on header words; a near-miss must still get the
    // grid, or a widening of that regex would silently restructure real data.
    const tableMd = `
| Item | Value |
| --- | --- |
| alpha | 1 |
`.trim();
    const frame = renderMarkdown(tableMd);
    expect(frame).toContain('┌');
    expect(frame).toContain('alpha');
  });

  it('keeps borders for a three-column table', () => {
    const tableMd = `
| Task | Status | Owner |
| --- | --- | --- |
| t1 | done | Apogee |
`.trim();
    const frame = renderMarkdown(tableMd);
    expect(frame).toContain('┌');
    expect(frame).toContain('Apogee');
  });

  it('renders every status branch of the checklist glyph', () => {
    const tableMd = `
| Task | Status |
| --- | --- |
| t1: Search docs | ✅ |
| t2: Fix the build | blocked |
| t3: Review PR | pending |
`.trim();
    const frame = renderMarkdown(tableMd);
    expect(frame).toContain('✓');
    expect(frame).toContain('!');
    expect(frame).toContain('·');
    // The model's own words survive: a glyph alone cannot tell "in progress"
    // from "deferred".
    expect(frame).toContain('blocked');
    expect(frame).toContain('pending');
  });

  it('renders an autolink as a bare URL, not angle brackets', () => {
    const tableMd = `
| Item | Detail |
| --- | --- |
| Source URL | <https://vite.dev/blog/announcing-vite8-1> |
`.trim();
    const frame = renderMarkdown(tableMd);
    expect(frame).toContain('https://vite.dev/blog/announcing-vite8-1');
    expect(frame).not.toContain('<https://');
  });

  it('degrades a bordered table to a plain list when the grid cannot fit', () => {
    // The degraded branch needs the layout input and the render canvas to agree;
    // ink-testing-library's fixed 100-column canvas made it unreachable.
    const tableMd = `
| Key | Value |
| --- | --- |
| alpha | some detail |
| beta | other detail |
`.trim();
    const wide = renderMarkdown(tableMd, 200);
    expect(wide).toContain('┌');

    const narrow = renderMarkdown(tableMd, 12);
    expect(narrow).not.toContain('┌');
    expect(narrow).toContain('alpha');
    expect(narrow).toContain('beta');
  });

  it('wraps long unbroken strings across lines within column width', () => {
    const longString = 'a'.repeat(100);
    const tableMd = `
| Col | Value |
| --- | --- |
| test | ${longString} |
`.trim();
    const frame = renderMarkdown(tableMd);
    expect(frame).not.toContain('…');
    expect(frame).toContain('test');
    // Check that the long string was wrapped into multiple lines
    const contentLines = frame.split('\n').filter((l) => l.includes('│') && !l.includes('Col') && !l.includes('Value'));
    expect(contentLines.length).toBeGreaterThan(1);
  });
});
