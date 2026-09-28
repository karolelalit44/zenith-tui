import React from 'react';
import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { ScenarioRenderer } from '../src/components/Display/Scenario/ScenarioRenderer';
import { estimateTokensForEvents, formatTokenCount } from '../src/services/api/tokenEstimationService';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ScenarioEvent, ToolStepEvent } from '../src/types/scenario';
import { convertHistoryToTurns } from '../src/utils/historyToTurns';
import { formatTurnCost, resolveTurnUsage } from '../src/utils/turnUsage';

describe('turnUsage & token estimation telemetry', () => {
  it('estimates tokens from tool_step params and tool name', () => {
    const toolEvent: ToolStepEvent = {
      kind: 'tool_step',
      id: 'step_1',
      tool: 'file_read',
      params: { path: 'src/components/Display/Scenario/SuccessCard.tsx' },
      success: true,
      output: '',
      error: '',
      metadata: {},
      pending: false,
    };
    const tokens = estimateTokensForEvents([toolEvent]);
    expect(tokens).toBeGreaterThan(0);
  });

  it('guarantees at least 1 token when non-empty content has fewer than 4 chars', () => {
    const shortEvent: ScenarioEvent = {
      kind: 'message',
      id: 'msg_short',
      text: 'hi',
    } as ScenarioEvent;
    const tokens = estimateTokensForEvents([shortEvent]);
    expect(tokens).toBe(1);
  });

  it('resolves turn usage accurately when server sends tokenInfo and elapsedMs', () => {
    const events: ScenarioEvent[] = [
      {
        kind: 'message',
        id: 'msg_1',
        text: 'hello',
      } as ScenarioEvent,
      {
        kind: 'success',
        id: 'succ_1',
        message: 'Completed',
        elapsedMs: 2500,
        tokenInfo: {
          used: 15400,
          remaining: 112600,
          total: 128000,
          percent: 0.12,
          estimated: false,
        },
      } as ScenarioEvent,
    ];

    const usage = resolveTurnUsage(events);
    expect(usage.tokens).toBe(15400);
    expect(usage.durationMs).toBe(2500);

    const costStr = formatTurnCost(usage);
    expect(costStr).toContain('+15.4K');
    expect(costStr).toContain('(2 s)');
  });

  it('resolves turn usage with fallback duration and estimated tokens when no success event exists', () => {
    const errorEvents: ScenarioEvent[] = [
      {
        kind: 'error',
        id: 'err_1',
        message: 'Backend connection timeout',
      } as ScenarioEvent,
    ];

    const usage = resolveTurnUsage(errorEvents);
    expect(usage.tokens).toBeGreaterThan(0);
    expect(usage.durationMs).toBe(1000);

    const costStr = formatTurnCost(usage);
    expect(costStr).toMatch(/\+\d+/);
    expect(costStr).toContain('(1 s)');
  });

  it('resolves turn usage when success has 0 used and 0 runTotal', () => {
    const events: ScenarioEvent[] = [
      {
        kind: 'tool_step',
        id: 'step_todo',
        tool: 'todo',
        params: { action: 'update', id: '1', status: 'completed' },
        success: true,
        output: 'Task completed',
        error: '',
        metadata: {},
        pending: false,
      },
      {
        kind: 'success',
        id: 'succ_zero',
        message: 'Completed',
        elapsedMs: 12000,
        tokenInfo: {
          used: 0,
          runTotal: 0,
          remaining: 0,
          total: 0,
          percent: 0,
        },
      } as ScenarioEvent,
    ];

    const usage = resolveTurnUsage(events);
    expect(usage.tokens).toBeGreaterThan(0);
    expect(usage.durationMs).toBe(12000);

    const costStr = formatTurnCost(usage);
    expect(costStr).toMatch(/\+\d+/);
    expect(costStr).toContain('(12 s)');
  });

  it('ensures convertHistoryToTurns synthesizes a success event with tokens and duration', () => {
    const messages = [
      {
        id: 'msg_user',
        role: 'user',
        content: 'hello',
        created_at: '2026-08-30T10:00:00Z',
      },
      {
        id: 'msg_assistant',
        role: 'assistant',
        content: 'world',
        created_at: '2026-08-30T10:00:01Z',
        events: [],
      },
    ];

    const turns = convertHistoryToTurns(messages, 'build');
    expect(turns).toHaveLength(1);
    const turn = turns[0];
    const successEvent = turn.events.find((e: ScenarioEvent) => e.kind === 'success');
    expect(successEvent).toBeDefined();
    expect(successEvent.elapsedMs).toBe(1000);
    expect(successEvent.tokenInfo?.used).toBeGreaterThan(0);

    const cost = formatTurnCost(resolveTurnUsage(turn.events));
    expect(cost).toContain('+');
    expect(cost).toContain('(1 s)');
  });

  it('renders status row with duration and tokens for error-only turns', () => {
    const errorEvents: ScenarioEvent[] = [
      {
        kind: 'error',
        id: 'err_test',
        message: 'Something went wrong',
      } as ScenarioEvent,
    ];

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer
          events={errorEvents}
          isRunning={false}
          isHistorical={true}
          thinkingCollapsed={false}
        />
      </ThemeProvider>,
    );

    const frame = lastFrame();
    expect(frame).toContain('tokens');
    expect(frame).toMatch(/\d+\s*s/);
  });

  it('renders live status row with duration and tokens for in-flight pending tool steps', () => {
    const pendingToolEvents: ScenarioEvent[] = [
      {
        kind: 'tool_step',
        id: 'step_live',
        tool: 'file_read',
        params: { path: 'package.json' },
        success: false,
        output: '',
        error: '',
        metadata: {},
        pending: true,
      } as ScenarioEvent,
    ];

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer
          events={pendingToolEvents}
          isRunning={true}
          isHistorical={false}
          thinkingCollapsed={false}
        />
      </ThemeProvider>,
    );

    const frame = lastFrame();
    expect(frame).toContain('tokens');
    expect(frame).toMatch(/\d+\s*s/);
  });
});
