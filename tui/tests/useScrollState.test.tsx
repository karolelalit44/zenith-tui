import { Box, Text } from 'ink';
import { render } from 'ink-testing-library';
// biome-ignore lint/correctness/noUnusedImports: React is required for JSX transform
import React, { useEffect } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { type UseScrollStateReturn, useScrollState } from '../src/hooks/useScrollState';

interface ProbeProps {
  onReady: (controls: UseScrollStateReturn) => void;
  viewportHeight?: number;
}

function ScrollProbe({ onReady, viewportHeight = 15 }: ProbeProps) {
  const controls = useScrollState(viewportHeight);

  useEffect(() => {
    onReady(controls);
  }, [controls, onReady]);

  return (
    <Box>
      <Text>{JSON.stringify(controls.scrollState)}</Text>
    </Box>
  );
}

describe('useScrollState hook', () => {
  it('initializes with default viewport height and zero offset', async () => {
    let captured: UseScrollStateReturn | null = null;
    render(
      <ScrollProbe
        onReady={(c) => {
          captured = c;
        }}
        viewportHeight={15}
      />,
    );
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(captured).not.toBeNull();
    expect(captured!.scrollState.isUserScrolled).toBe(false);
    expect(captured!.scrollState.contentHeight).toBe(0);
  });

  it('auto-follows content height growth when user is not scrolled', async () => {
    let captured: UseScrollStateReturn | null = null;
    const { rerender } = render(
      <ScrollProbe
        onReady={(c) => {
          captured = c;
        }}
        viewportHeight={10}
      />,
    );
    await new Promise((resolve) => setTimeout(resolve, 20));

    captured!.updateContentHeight(25);
    rerender(
      <ScrollProbe
        onReady={(c) => {
          captured = c;
        }}
        viewportHeight={10}
      />,
    );
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(captured!.scrollState.contentHeight).toBe(25);
    const maxOffset = Math.max(0, 25 - captured!.scrollState.viewportHeight);
    expect(captured!.scrollState.scrollOffset).toBe(maxOffset);
    expect(captured!.scrollState.isUserScrolled).toBe(false);
  });

  it('scrolls up from the bottom and locks auto-scroll position', async () => {
    let captured: UseScrollStateReturn | null = null;
    const { rerender } = render(
      <ScrollProbe
        onReady={(c) => {
          captured = c;
        }}
        viewportHeight={10}
      />,
    );
    await new Promise((resolve) => setTimeout(resolve, 20));

    captured!.updateContentHeight(30);
    rerender(
      <ScrollProbe
        onReady={(c) => {
          captured = c;
        }}
        viewportHeight={10}
      />,
    );
    await new Promise((resolve) => setTimeout(resolve, 20));

    const initialOffset = captured!.scrollState.scrollOffset;
    expect(initialOffset).toBeGreaterThan(0);

    captured!.scrollUp(5);
    rerender(
      <ScrollProbe
        onReady={(c) => {
          captured = c;
        }}
        viewportHeight={10}
      />,
    );
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(captured!.scrollState.isUserScrolled).toBe(true);
    expect(captured!.scrollState.scrollOffset).toBe(initialOffset - 5);

    // Further streaming growth does NOT hijack the user's scroll offset
    captured!.updateContentHeight(50);
    rerender(
      <ScrollProbe
        onReady={(c) => {
          captured = c;
        }}
        viewportHeight={10}
      />,
    );
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(captured!.scrollState.scrollOffset).toBe(initialOffset - 5);
    expect(captured!.scrollState.contentHeight).toBe(50);
  });

  it('resumes auto-scroll when scrolled back to the bottom', async () => {
    let captured: UseScrollStateReturn | null = null;
    const { rerender } = render(
      <ScrollProbe
        onReady={(c) => {
          captured = c;
        }}
        viewportHeight={10}
      />,
    );
    await new Promise((resolve) => setTimeout(resolve, 20));

    captured!.updateContentHeight(30);
    captured!.scrollUp(10);
    rerender(
      <ScrollProbe
        onReady={(c) => {
          captured = c;
        }}
        viewportHeight={10}
      />,
    );
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(captured!.scrollState.isUserScrolled).toBe(true);

    captured!.scrollToBottom();
    rerender(
      <ScrollProbe
        onReady={(c) => {
          captured = c;
        }}
        viewportHeight={10}
      />,
    );
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(captured!.scrollState.isUserScrolled).toBe(false);
    const maxOffset = Math.max(0, 30 - captured!.scrollState.viewportHeight);
    expect(captured!.scrollState.scrollOffset).toBe(maxOffset);
  });

  it('clamps a user scroll offset when the terminal grows taller', async () => {
    // `process.stdout.rows` and the module-level resize listener set in
    // useTerminalDimensions are shared by every test in the worker, so a stub
    // left installed (or a resize emitted here) leaks into whichever file runs
    // next. Restore in a finally and unmount before returning.
    const originalRows = Object.getOwnPropertyDescriptor(process.stdout, 'rows');
    const stub = (rows: number) =>
      Object.defineProperty(process.stdout, 'rows', { configurable: true, get: () => rows });

    let captured: UseScrollStateReturn | null = null;
    const app = render(
      <ScrollProbe
        onReady={(c) => {
          captured = c;
        }}
        viewportHeight={10}
      />,
    );
    try {
      stub(24);
      await vi.waitFor(() => {
        expect(captured!.scrollState.viewportHeight).toBe(15);
      });

      captured!.updateContentHeight(60);
      captured!.scrollUp(10);
      await vi.waitFor(() => {
        expect(captured!.scrollState.isUserScrolled).toBe(true);
      });

      stub(80);
      process.stdout.emit('resize');
      // Poll rather than sleep a fixed interval: the resize arrives outside
      // React, so how long the re-render takes depends on what else the worker
      // is running. A fixed wait passed or failed depending on the load.
      await vi.waitFor(() => {
        expect(captured!.scrollState.viewportHeight).toBe(71);
      });
      expect(captured!.scrollState.scrollOffset).toBe(0);
      expect(captured!.scrollState.isUserScrolled).toBe(false);
    } finally {
      app.unmount();
      if (originalRows) Object.defineProperty(process.stdout, 'rows', originalRows);
      else delete (process.stdout as { rows?: number }).rows;
    }
  });
});
