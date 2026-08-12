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
    expect(frame).not.toMatch(/[^\s]\s{2,}/);
  });
});
