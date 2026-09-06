import { render } from 'ink-testing-library';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MultiLineTextInput } from '../src/components/Input/MultiLineTextInput';

import { ThemeProvider } from '../src/theme/ThemeContext';

const cleanups: Array<() => void> = [];

function mount(node: React.ReactNode) {
  const app = render(node);
  cleanups.push(app.unmount);
  return app;
}

describe('MultiLineTextInput', () => {
  afterEach(() => {
    for (const unmount of cleanups.splice(0)) unmount();
    vi.clearAllMocks();
  });

  it('accumulates multi-chunk pastes delivered in the same tick instead of overwriting', () => {
    const onChange = vi.fn();
    const onSubmit = vi.fn();
    const app = mount(<MultiLineTextInput value="" onChange={onChange} onSubmit={onSubmit} />);

    app.stdin.write('part-one-');
    app.stdin.write('part-two-');
    app.stdin.write('part-three');

    expect(onChange).toHaveBeenLastCalledWith('part-one-part-two-part-three', 28);
  });

  it('submits the full accumulated paste value on Enter', () => {
    const onChange = vi.fn();
    const onSubmit = vi.fn();
    const app = mount(<MultiLineTextInput value="" onChange={onChange} onSubmit={onSubmit} />);

    app.stdin.write('first-chunk');
    app.stdin.write('second-chunk');
    app.stdin.write('\r');

    expect(onSubmit).toHaveBeenCalledWith('first-chunksecond-chunk');
  });

  it('renders @mention tokens within the input text', () => {
    const onChange = vi.fn();
    const onSubmit = vi.fn();
    const app = mount(
      <ThemeProvider>
        <MultiLineTextInput value="Review @agent-aegis.md please" onChange={onChange} onSubmit={onSubmit} />
      </ThemeProvider>,
    );

    const frame = app.lastFrame();
    expect(frame).toContain('@agent-aegis.md');
    expect(frame).toContain('Review');
    expect(frame).toContain('please');
  });
});
