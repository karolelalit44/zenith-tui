import React from 'react';
import { expect, test } from 'vitest';
import { render } from 'ink-testing-library';
import { App } from '../src/App';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

test('App opens directly to Welcome + Input (no mode selection screen)', async () => {
  const { lastFrame, unmount } = render(<App />);

  const frame = lastFrame();
  expect(frame).toContain('1.0.0');
  expect(frame).toContain('SYSTEM STATUS');
  expect(frame).toContain('BUILD');
  expect(frame).toContain('Ask');
  expect(frame).toContain('>');
  unmount();
});

test('Input is ready immediately on startup', async () => {
  const { lastFrame, stdin, unmount } = render(<App />);

  expect(lastFrame()).toContain('>');

  stdin.write('hello');
  await wait(300);
  expect(lastFrame()).toContain('hello');
  unmount();
});

test('Submitting a prompt triggers scenario', async () => {
  const { lastFrame, stdin, unmount } = render(<App />);

  stdin.write('create a todo app');
  await wait(300);
  stdin.write('\r');
  await wait(500);

  expect(lastFrame()).toContain('Thinking');
  unmount();
});

test('/mode command opens mode selector overlay', async () => {
  const { lastFrame, stdin, unmount } = render(<App />);

  stdin.write('/mode');
  await wait(200);
  stdin.write('\r');
  await wait(300);

  expect(lastFrame()).toContain('Select Mode');
  expect(lastFrame()).toContain('CHOOSE OPERATING MODE');
  expect(lastFrame()).toContain('Plan');
  expect(lastFrame()).toContain('Build');
  unmount();
});

test('Mode selection changes current mode', async () => {
  const { lastFrame, stdin, unmount } = render(<App />);

  // Open mode selector
  stdin.write('/mode');
  await wait(200);
  stdin.write('\r');
  await wait(300);

  // Select Plan (first option, up arrow from Build)
  stdin.write('\x1B[A');
  await wait(100);
  stdin.write('\r');
  await wait(300);

  // Should show Plan mode
  expect(lastFrame()).toContain('PLAN');
  unmount();
});

test('Escape closes mode selector without changing mode', async () => {
  const { lastFrame, stdin, unmount } = render(<App />);

  // Open mode selector
  stdin.write('/mode');
  await wait(200);
  stdin.write('\r');
  await wait(300);

  // Press Escape
  stdin.write('\x1B');
  await wait(300);

  // Should still be Build mode
  expect(lastFrame()).toContain('BUILD');
  unmount();
});

test('Escape during scenario stops execution', async () => {
  const { lastFrame, stdin, unmount } = render(<App />);

  stdin.write('test');
  await wait(200);
  stdin.write('\r');
  await wait(500);

  expect(lastFrame()).toContain('Thinking');

  stdin.write('\x1B');
  await wait(300);

  expect(lastFrame()).toContain('>');
  unmount();
});

test('Full Build Scenario end-to-end', async () => {
  const { lastFrame, stdin, unmount } = render(<App />);

  // Submit prompt
  stdin.write('create a todo app');
  await wait(400);
  stdin.write('\r');
  await wait(1200);

  expect(lastFrame()).toContain('Thinking');

  await wait(5000);
  expect(lastFrame()).toContain('New File');

  await wait(14000);
  expect(lastFrame()).toContain('>');
  unmount();
}, 30000);

test('Full Plan Scenario end-to-end', async () => {
  const { lastFrame, stdin, unmount } = render(<App />);

  // Switch to Plan mode first via /mode
  stdin.write('/mode');
  await wait(400);
  stdin.write('\r');
  await wait(400);
  stdin.write('\x1B[A');
  await wait(200);
  stdin.write('\r');
  await wait(500);

  // Submit prompt
  stdin.write('design a REST API');
  await wait(400);
  stdin.write('\r');
  await wait(1200);

  expect(lastFrame()).toContain('Thinking');

  await wait(7000);
  expect(lastFrame()).toContain('>');
  unmount();
}, 30000);
