import { render } from 'ink-testing-library';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { UserMessageBlock } from '../src/components/Display/Scenario/UserMessageBlock';
import { CommandInput } from '../src/components/Input/CommandInput';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { FileAttachment } from '../src/types/scenario';

const cleanups: Array<() => void> = [];

function mount(node: React.ReactNode) {
  const app = render(node);
  cleanups.push(app.unmount);
  return app;
}

describe('Composer File Attachments & UserMessageBlock', () => {
  afterEach(() => {
    for (const unmount of cleanups.splice(0)) unmount();
    vi.clearAllMocks();
  });

  it('renders attachment chips inside the composer dock', () => {
    const attachments: FileAttachment[] = [
      {
        path: 'agent-aegis.md',
        name: 'agent-aegis.md',
        mimeType: 'text/markdown',
        size: 7577, // ~7.4 KB
        kind: 'file',
      },
      {
        path: 'server',
        name: 'server',
        mimeType: 'inode/directory',
        size: 0,
        kind: 'folder',
      },
    ];

    const onRemoveAttachment = vi.fn();
    const app = mount(
      <ThemeProvider>
        <CommandInput
          input=""
          onInputChange={vi.fn()}
          onSubmit={vi.fn()}
          attachments={attachments}
          onRemoveAttachment={onRemoveAttachment}
        />
      </ThemeProvider>,
    );

    const frame = app.lastFrame() || '';
    expect(frame).toContain('agent-aegis.md');
    expect(frame).toContain('7.4 KB');
    expect(frame).toContain('server');
    expect(frame).toContain('📄');
    expect(frame).toContain('📁');
    expect(frame).toContain('×');
  });

  it('removes the last attachment when Backspace is pressed on an empty prompt', () => {
    const attachments: FileAttachment[] = [
      {
        path: 'foo.ts',
        name: 'foo.ts',
        mimeType: 'text/typescript',
        size: 1024,
        kind: 'file',
      },
    ];

    const onRemoveAttachment = vi.fn();
    const app = mount(
      <ThemeProvider>
        <CommandInput
          input=""
          onInputChange={vi.fn()}
          onSubmit={vi.fn()}
          attachments={attachments}
          onRemoveAttachment={onRemoveAttachment}
        />
      </ThemeProvider>,
    );

    app.stdin.write('\x08'); // Backspace
    expect(onRemoveAttachment).toHaveBeenCalledWith(0);
  });

  it('clears attachments and input when Escape is pressed on a prompt with attachments', async () => {
    const attachments: FileAttachment[] = [
      {
        path: 'bar.ts',
        name: 'bar.ts',
        mimeType: 'text/typescript',
        size: 2048,
        kind: 'file',
      },
    ];

    const onClearAttachments = vi.fn();
    const onClearInput = vi.fn();
    const onInputChange = vi.fn();
    const app = mount(
      <ThemeProvider>
        <CommandInput
          input="some drafted text"
          onInputChange={onInputChange}
          onSubmit={vi.fn()}
          attachments={attachments}
          onClearInput={onClearInput}
          onClearAttachments={onClearAttachments}
        />
      </ThemeProvider>,
    );

    app.stdin.write('\x1B'); // Escape
    await new Promise((resolve) => setTimeout(resolve, 600));
    expect(onInputChange).toHaveBeenCalledWith('', 0);
    expect(onClearInput).toHaveBeenCalled();
    expect(onClearAttachments).toHaveBeenCalled();
  });

  it('clears attachments when Escape is pressed on an empty prompt', async () => {
    const attachments: FileAttachment[] = [
      {
        path: 'bar.ts',
        name: 'bar.ts',
        mimeType: 'text/typescript',
        size: 2048,
        kind: 'file',
      },
    ];

    const onClearAttachments = vi.fn();
    const app = mount(
      <ThemeProvider>
        <CommandInput
          input=""
          onInputChange={vi.fn()}
          onSubmit={vi.fn()}
          attachments={attachments}
          onClearAttachments={onClearAttachments}
        />
      </ThemeProvider>,
    );

    app.stdin.write('\x1B'); // Escape
    await new Promise((resolve) => setTimeout(resolve, 600));
    expect(onClearAttachments).toHaveBeenCalled();
  });

  it('does not render attached file badges below user prompt in UserMessageBlock and preserves @mentions', () => {
    const attachments: FileAttachment[] = [
      {
        path: 'agent-aegis.md',
        name: 'agent-aegis.md',
        mimeType: 'text/markdown',
        size: 7577,
        kind: 'file',
      },
      {
        path: 'server',
        name: 'server',
        mimeType: 'inode/directory',
        size: 0,
        kind: 'folder',
      },
    ];

    const app = mount(
      <ThemeProvider>
        <UserMessageBlock
          prompt="@agent-aegis.md Investigate backend architecture"
          model="Claude 3.7 Sonnet"
          timestamp="12:30"
          attachments={attachments}
        />
      </ThemeProvider>,
    );

    const frame = app.lastFrame() || '';
    expect(frame).toContain('@agent-aegis.md');
    expect(frame).toContain('Investigate backend architecture');
    expect(frame).not.toContain('Attached:');
    expect(frame).not.toContain('7.4 KB');
    expect(frame).not.toContain('📄');
    expect(frame).not.toContain('📁');
  });
});
