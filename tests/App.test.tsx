import React from 'react';
import { expect, test } from 'vitest';
import { render } from 'ink-testing-library';
import { App } from '../src/App';

test('App Happy Flow End-to-End', async () => {
  const { lastFrame, stdin } = render(<App />);
  
  // 1. Boot State
  expect(lastFrame()).toContain('v1.0.0');
  expect(lastFrame()).toContain('SYSTEM STATUS');
  
  // 2. Open Autocomplete
  stdin.write('/');
  
  // Wait a tick for React state to update
  await new Promise((resolve) => setTimeout(resolve, 100));
  expect(lastFrame()).toContain('/add-dir');
  
  // 3. Filter for plugin and select it via Autocomplete
  stdin.write('plugin');
  await new Promise((resolve) => setTimeout(resolve, 100));
  
  // Hit enter to select the autocomplete option
  stdin.write('\r');
  await new Promise((resolve) => setTimeout(resolve, 100));
  expect(lastFrame()).toContain('Discover plugins');
  
  // 4. Hit Enter inside Plugin Modal to trigger Mock
  stdin.write('\r');
  await new Promise((resolve) => setTimeout(resolve, 100));
  
  // Now we should be in 'thinking' state for plugins
  expect(lastFrame()).toContain('Fetching registry...');
});

test('App MockEngine Branching: /add-dir and /clear', async () => {
  const { lastFrame, stdin } = render(<App />);
  
  // Test /add-dir
  stdin.write('/add-dir');
  await new Promise((resolve) => setTimeout(resolve, 100));
  stdin.write('\r'); // trigger enter
  await new Promise((resolve) => setTimeout(resolve, 100));
  
  expect(lastFrame()).toContain('Scanning file system...');
  
  // Wait for command to finish
  await new Promise((resolve) => setTimeout(resolve, 1500));
  expect(lastFrame()).toContain('Directory mapped and vectorized.');

  // Test /clear
  stdin.write('/clear');
  await new Promise((resolve) => setTimeout(resolve, 100));
  stdin.write('\r');
  await new Promise((resolve) => setTimeout(resolve, 100));
  
  // History should be wiped, so the WelcomeHeader should be visible again
  expect(lastFrame()).toContain('v1.0.0');
});
