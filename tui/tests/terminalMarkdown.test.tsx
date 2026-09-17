import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { TerminalMarkdown } from '../src/components/Display/Scenario/TerminalMarkdown';
import { ThemeProvider } from '../src/theme/ThemeContext';

function stripAnsi(s: string): string {
  // eslint-disable-next-line no-control-regex
  return s.replace(/\u001b\[[0-9;]*m/g, '');
}

function renderMarkdown(content: string) {
  const { lastFrame } = render(
    <ThemeProvider>
      <TerminalMarkdown content={content} />
    </ThemeProvider>,
  );
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
