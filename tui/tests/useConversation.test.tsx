import { Box, Text } from 'ink';
import { render } from 'ink-testing-library';
// biome-ignore lint/correctness/noUnusedImports: React is required for JSX transform (jsx: "react")
import React, { useEffect } from 'react';
import { expect, test } from 'vitest';
import { useConversation } from '../src/hooks/useConversation';
import type { ScenarioEvent } from '../src/types/scenario';

interface ProbeResult {
  runTokens: number;
  runPrompt: number;
  runCompletion: number;
  runEstimated: boolean;
  contextInfo: { used: number; total: number; windowEstimated: boolean } | null;
}

function Probe({ events }: { events: ScenarioEvent[] }) {
  const { runTokens, runPrompt, runCompletion, runEstimated, contextInfo, addTurn, completeActiveTurn } =
    useConversation();

  useEffect(() => {
    addTurn('probe', 'build', 'test-model');
    completeActiveTurn(events);
  }, [addTurn, completeActiveTurn, events]);

  const result: ProbeResult = {
    runTokens,
    runPrompt,
    runCompletion,
    runEstimated,
    contextInfo: contextInfo
      ? { used: contextInfo.used, total: contextInfo.total, windowEstimated: contextInfo.windowEstimated }
      : null,
  };
  return (
    <Box>
      <Text>{JSON.stringify(result)}</Text>
    </Box>
  );
}

async function readResult(events: ScenarioEvent[]): Promise<ProbeResult> {
  const { lastFrame } = render(<Probe events={events} />);
  await new Promise((resolve) => setTimeout(resolve, 10));
  // ink-testing-library caps the render width at 100 columns and keeps ANSI
  // codes in the raw frame, so strip both before parsing the probe JSON.
  const frame = lastFrame()
    .replace(/\u001b\[[0-9;]*m/g, '')
    .replace(/[\r\n]+/g, '')
    .trim();
  return JSON.parse(frame) as ProbeResult;
}

const modernSuccess: ScenarioEvent = {
  kind: 'success',
  id: 'evt_modern',
  message: 'done',
  elapsedMs: 1000,
  tokenInfo: {
    used: 50_000,
    remaining: 78_000,
    total: 128_000,
    percent: 0.390625,
    estimated: false,
    windowEstimated: true,
    runTotal: 52_316,
    runPrompt: 1_821,
    runCompletion: 50_495,
  },
};

const legacyEstimatedSuccess: ScenarioEvent = {
  kind: 'success',
  id: 'evt_legacy_est',
  message: 'done',
  elapsedMs: 1000,
  tokenInfo: {
    used: 1_743,
    remaining: 126_257,
    total: 128_000,
    percent: 0.0136,
    estimated: true,
  },
};

const noTokenInfoSuccess: ScenarioEvent = {
  kind: 'success',
  id: 'evt_no_ti',
  message: 'done',
  elapsedMs: 1000,
};

test('modern success: run telemetry from runTotal, composed snapshot exposed', async () => {
  const result = await readResult([modernSuccess]);
  expect(result.runTokens).toBe(52_316);
  expect(result.runPrompt).toBe(1_821);
  expect(result.runCompletion).toBe(50_495);
  expect(result.runEstimated).toBe(false);
  expect(result.contextInfo).toEqual({ used: 50_000, total: 128_000, windowEstimated: true });
});

test('legacy estimated success: count falls back, snapshot kept, usage flagged estimated', async () => {
  const result = await readResult([legacyEstimatedSuccess]);
  // Without runTotal the legacy count derives from the composed/estimate path.
  expect(result.runTokens).toBe(1_743);
  expect(result.runPrompt).toBe(0);
  expect(result.runCompletion).toBe(0);
  expect(result.runEstimated).toBe(true);
  expect(result.contextInfo).toEqual({ used: 1_743, total: 128_000, windowEstimated: false });
});

test('legacy success without tokenInfo: char estimate and no context snapshot', async () => {
  const result = await readResult([
    {
      kind: 'message',
      id: 'evt_msg',
      text: 'hello world, this is a long assistant message for the estimator',
      partial: false,
    },
    noTokenInfoSuccess,
  ]);
  expect(result.runTokens).toBeGreaterThan(0);
  expect(result.runEstimated).toBe(true);
  expect(result.contextInfo).toBeNull();
});
