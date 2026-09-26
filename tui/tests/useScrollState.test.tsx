import { Box, Text } from 'ink';
import { render } from 'ink-testing-library';
// biome-ignore lint/correctness/noUnusedImports: React is required for JSX transform
import React, { useEffect } from 'react';
import { describe, expect, it } from 'vitest';
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
});
