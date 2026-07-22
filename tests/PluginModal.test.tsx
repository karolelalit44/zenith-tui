import React from 'react';
import { expect, test } from 'vitest';
import { render } from 'ink-testing-library';
import { PluginsScreen } from '../src/screens/Settings/Plugins/PluginsScreen';

test('PluginsScreen renders tabs and search bar', () => {
  const { lastFrame } = render(<PluginsScreen onClose={() => {}} onTriggerMock={() => {}} />);
  
  const frame = lastFrame();
  
  // Verify Tabs
  expect(frame).toContain('Discover');
  expect(frame).toContain('Installed');
  expect(frame).toContain('arrows to cycle');
  expect(frame).toContain('enter to run');
  expect(frame).toContain('esc to close');
  
  // Verify Search Bar
  expect(frame).toContain('Search:');
  
  // Verify Plugins
  expect(frame).toContain('context7');
});
