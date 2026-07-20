import React from 'react';
import { expect, test } from 'vitest';
import { render } from 'ink-testing-library';
import { PluginModal } from '../src/components/PluginModal';

test('PluginModal renders tabs and search bar', () => {
  const { lastFrame } = render(<PluginModal onClose={() => {}} onTriggerMock={() => {}} />);
  
  const frame = lastFrame();
  
  // Verify Tabs
  expect(frame).toContain('Discover');
  expect(frame).toContain('Installed');
  expect(frame).toContain('(arrows to cycle, enter to run, esc to close)');
  
  // Verify Search Bar
  expect(frame).toContain('⌕ Search:');
  
  // Verify Plugins
  expect(frame).toContain('context7');
});
