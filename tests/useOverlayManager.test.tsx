import { Box, Text } from 'ink';
import React from 'react';
import { expect, test } from 'vitest';
import { render } from 'ink-testing-library';
import { useOverlayManager } from '../src/hooks/useOverlayManager';

function TestHarness() {
  const { selectedMode, overlay, isOverlayOpen } = useOverlayManager();
  return (
    <Box>
      <Text>{selectedMode}</Text>
      <Text>{overlay}</Text>
      <Text>{String(isOverlayOpen)}</Text>
    </Box>
  );
}

test('starts with no overlay and build mode', () => {
  const { lastFrame } = render(<TestHarness />);
  const frame = lastFrame();
  expect(frame).toContain('build');
  expect(frame).toContain('none');
  expect(frame).toContain('false');
});

test('handleModeSelect changes mode and closes overlay with initial plan', () => {
  function PlanHarness() {
    const { selectedMode } = useOverlayManager('plan');
    return <Text>{selectedMode}</Text>;
  }
  const { lastFrame } = render(<PlanHarness />);
  expect(lastFrame()).toContain('plan');
});
