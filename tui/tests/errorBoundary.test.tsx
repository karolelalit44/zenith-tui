import { Text } from 'ink';
import { render } from 'ink-testing-library';
import React from 'react';
import { expect, test } from 'vitest';
import { ErrorBoundary } from '../src/components/ui/ErrorBoundary';

function Boom(): React.ReactNode {
  throw new Error('boom: render failure');
}

test('ErrorBoundary shows a fallback instead of crashing when a child throws', () => {
  const { lastFrame, unmount } = render(
    <ErrorBoundary>
      <Boom />
    </ErrorBoundary>,
  );

  const frame = lastFrame();
  expect(frame).toContain('RUNTIME ERROR');
  expect(frame).toContain('boom: render failure');
  // Regression: the boundary used to re-throw inside its own fallback on a
  // non-TTY stdin and die with "Maximum update depth exceeded".
  expect(frame).not.toContain('Maximum update depth exceeded');

  unmount();
});

test('ErrorBoundary renders children normally when no error is thrown', () => {
  const { lastFrame, unmount } = render(
    <ErrorBoundary>
      <Text>all good</Text>
    </ErrorBoundary>,
  );

  expect(lastFrame()).toContain('all good');
  expect(lastFrame()).not.toContain('RUNTIME ERROR');

  unmount();
});
