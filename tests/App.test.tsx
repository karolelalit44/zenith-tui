import React from 'react';
import { expect, test } from 'vitest';
import { render } from 'ink-testing-library';
import { App } from '../src/App';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

test('App Happy Flow End-to-End', async () => {
  const { lastFrame, stdin } = render(<App />);
  
  // 1. Boot State - Welcome screen
  expect(lastFrame()).toContain('1.0.0');
  expect(lastFrame()).toContain('SYSTEM STATUS');
  
  // 2. Open Autocomplete
  stdin.write('/');
  await wait(100);
  expect(lastFrame()).toContain('/add-dir');
  
  // 3. Filter for plugin and select it via Autocomplete
  stdin.write('plugin');
  await wait(100);
  
  stdin.write('\r');
  await wait(100);
  expect(lastFrame()).toContain('Discover plugins');
  
  // 4. Hit Enter inside Plugin Modal to trigger Mock
  stdin.write('\r');
  await wait(100);
  
  // Should show thinking indicator
  expect(lastFrame()).toContain('Fetching');
  
  // Wait for completion
  await wait(2500);
  expect(lastFrame()).toContain('Plugin Verified');
  expect(lastFrame()).toContain('DONE');
}, 10000);

test('App MockEngine: /add-dir with structured output', async () => {
  const { lastFrame, stdin } = render(<App />);
  
  // Test /add-dir
  stdin.write('/add-dir');
  await wait(100);
  stdin.write('\r');
  await wait(100);
  
  // Check for the Thinking component's scanning phase
  expect(lastFrame()).toContain('Scanning');
  
  // Wait for command to finish
  await wait(2000);
  expect(lastFrame()).toContain('Workspace Synced');
  expect(lastFrame()).toContain('DONE');
  expect(lastFrame()).toContain('Directory mapped and vectorized.');
}, 10000);

test('App MockEngine: /clear resets to welcome', async () => {
  const { lastFrame, stdin } = render(<App />);
  
  // Execute a command first
  stdin.write('/plugin');
  await wait(100);
  stdin.write('\r');
  await wait(2500);
  
  // Now clear
  stdin.write('/clear');
  await wait(100);
  stdin.write('\r');
  await wait(100);
  
  // History should be wiped, so the WelcomeHeader should be visible again
  expect(lastFrame()).toContain('1.0.0');
  expect(lastFrame()).toContain('SYSTEM STATUS');
}, 10000);

test('App MockEngine: default command shows file edit output', async () => {
  const { lastFrame, stdin } = render(<App />);
  
  // Type a regular message (not a command)
  stdin.write('fix the bug in auth module');
  await wait(100);
  stdin.write('\r');
  await wait(100);
  
  // Should show thinking
  expect(lastFrame()).toContain('Thinking');
  
  // Wait for completion (delays are randomized, give plenty of time)
  await wait(3000);
  expect(lastFrame()).toContain('File Updated');
  expect(lastFrame()).toContain('src/engine.ts');
  expect(lastFrame()).toContain('DONE');
}, 10000);

test('App MockEngine: /build shows build result output', async () => {
  const { lastFrame, stdin } = render(<App />);
  
  stdin.write('/build');
  await wait(100);
  stdin.write('\r');
  await wait(100);
  
  // Should show building phase
  expect(lastFrame()).toContain('Building');
  
  // Wait for completion (delays are randomized, give plenty of time)
  await wait(5000);
  expect(lastFrame()).toContain('Build Complete');
  expect(lastFrame()).toContain('DONE');
  expect(lastFrame()).toContain('Resolving dependencies');
  expect(lastFrame()).toContain('Compiling TypeScript');
  expect(lastFrame()).toContain('Minifying assets');
}, 15000);

test('Full E2E: Welcome -> Command -> Output -> Another Command -> Clear', async () => {
  const { lastFrame, stdin } = render(<App />);
  
  // Step 1: Verify welcome screen
  expect(lastFrame()).toContain('1.0.0');
  expect(lastFrame()).toContain('SYSTEM STATUS');
  
  // Step 2: Execute /build command
  stdin.write('/build');
  await wait(100);
  stdin.write('\r');
  await wait(100);
  expect(lastFrame()).toContain('Building');
  
  // Wait for build to complete
  await wait(5000);
  expect(lastFrame()).toContain('Build Complete');
  
  // Step 3: Execute /plugin command
  stdin.write('/plugin');
  await wait(100);
  stdin.write('\r');
  await wait(100);
  expect(lastFrame()).toContain('Fetching');
  
  // Wait for plugin to complete
  await wait(2500);
  expect(lastFrame()).toContain('Plugin Verified');
  
  // Step 4: Execute a default command (file edit)
  stdin.write('refactor the auth module');
  await wait(100);
  stdin.write('\r');
  await wait(100);
  expect(lastFrame()).toContain('Thinking');
  
  // Wait for file edit to complete
  await wait(3000);
  expect(lastFrame()).toContain('File Updated');
  expect(lastFrame()).toContain('src/engine.ts');
  
  // Step 5: Clear all history
  stdin.write('/clear');
  await wait(100);
  stdin.write('\r');
  await wait(100);
  
  // Should be back to welcome screen
  expect(lastFrame()).toContain('1.0.0');
  expect(lastFrame()).toContain('SYSTEM STATUS');
}, 20000);
