import { describe, expect, test, vi } from 'vitest';
import { getEventDelay } from '../src/services/scenario/delays';
import { getScenarioForPrompt } from '../src/services/scenario/matcher';
import { runScenario } from '../src/services/scenario/engine';
import type { ScenarioEvent, Scenario } from '../src/types/scenario';

describe('getEventDelay', () => {
  test('thinking uses event duration', () => {
    expect(getEventDelay({ kind: 'thinking', text: '', duration: 1000 })).toBe(1000);
  });

  test('file_create returns 800', () => {
    expect(getEventDelay({ kind: 'file_create', path: 'x', content: '' })).toBe(800);
  });

  test('file_edit returns 600', () => {
    expect(getEventDelay({ kind: 'file_edit', path: 'x', content: '' })).toBe(600);
  });

  test('file_delete returns 400', () => {
    expect(getEventDelay({ kind: 'file_delete', path: 'x' })).toBe(400);
  });

  test('terminal uses duration + 400', () => {
    expect(getEventDelay({ kind: 'terminal', command: 'ls', output: '', duration: 500 })).toBe(900);
  });

  test('error returns 600', () => {
    expect(getEventDelay({ kind: 'error', message: 'fail' })).toBe(600);
  });

  test('warning returns 400', () => {
    expect(getEventDelay({ kind: 'warning', message: 'warn' })).toBe(400);
  });

  test('retry returns 400', () => {
    expect(getEventDelay({ kind: 'retry', attempt: 1, message: 'retrying' })).toBe(400);
  });

  test('success returns 300', () => {
    expect(getEventDelay({ kind: 'success', message: 'done' })).toBe(300);
  });

  test('summary returns 200', () => {
    expect(getEventDelay({ kind: 'summary', text: 'summary' })).toBe(200);
  });

  test('message returns 300', () => {
    expect(getEventDelay({ kind: 'message', text: 'msg' })).toBe(300);
  });

  test('progress returns 400', () => {
    expect(getEventDelay({ kind: 'progress', percent: 50, text: '' })).toBe(400);
  });

  test('waiting uses event duration', () => {
    expect(getEventDelay({ kind: 'waiting', text: '', duration: 2000 })).toBe(2000);
  });

  test('test_execution returns 1000', () => {
    expect(getEventDelay({ kind: 'test_execution', suite: '', results: { passed: 0, failed: 0, total: 0 } })).toBe(1000);
  });

  test('build_step uses duration + 300 or default', () => {
    expect(getEventDelay({ kind: 'build_step', name: '', status: 'running', duration: 700 })).toBe(1000);
    expect(getEventDelay({ kind: 'build_step', name: '', status: 'running' })).toBe(800);
  });

  test('deployment returns 800', () => {
    expect(getEventDelay({ kind: 'deployment', environment: 'prod', status: 'success', url: '' })).toBe(800);
  });

  test('analysis uses sections.length * 200 + 300', () => {
    expect(getEventDelay({ kind: 'analysis', sections: [{ title: 'a', body: '' }] })).toBe(500);
    expect(getEventDelay({ kind: 'analysis', sections: [{ title: 'a', body: '' }, { title: 'b', body: '' }, { title: 'c', body: '' }] })).toBe(900);
  });
});

describe('getScenarioForPrompt', () => {
  test('provider error keywords return provider error scenario', () => {
    const s = getScenarioForPrompt('rate limit error', 'build');
    expect(s.events.some((e) => e.kind === 'error')).toBe(true);
  });

  test('system error keywords return system error scenario', () => {
    const s = getScenarioForPrompt('permission denied', 'build');
    expect(s.events.some((e) => e.kind === 'error')).toBe(true);
  });

  test('mode mismatch when plan mode has build keywords', () => {
    const s = getScenarioForPrompt('generate code for feature', 'plan');
    expect(s.events.some((e) => e.kind === 'mode_mismatch')).toBe(true);
  });

  test('[plan] override switches to plan mode', () => {
    const s = getScenarioForPrompt('build a react app [plan]', 'build');
    expect(s.events.some((e) => e.kind === 'analysis')).toBe(true);
  });

  test('[build] override switches to build mode', () => {
    const s = getScenarioForPrompt('design an API [build]', 'plan');
    expect(s.events.some((e) => e.kind === 'terminal')).toBe(true);
  });

  test('react keywords match react scenario', () => {
    const build = getScenarioForPrompt('build a react dashboard', 'build');
    const plan = getScenarioForPrompt('plan a react dashboard', 'plan');
    expect(build.events.length).toBeGreaterThan(0);
    expect(plan.events.length).toBeGreaterThan(0);
  });

  test('docker keywords match docker scenario', () => {
    const s = getScenarioForPrompt('containerize with docker', 'build');
    expect(s.events.some((e) => e.kind === 'terminal')).toBe(true);
  });

  test('ci/cd keywords match pipeline scenario', () => {
    const s = getScenarioForPrompt('set up github actions pipeline', 'build');
    expect(s.events.some((e) => e.kind === 'file_create' || e.kind === 'build_step')).toBe(true);
  });

  test('api keywords match api scenario', () => {
    const s = getScenarioForPrompt('create a rest api endpoint', 'build');
    expect(s.events.some((e) => e.kind === 'terminal')).toBe(true);
  });

  test('no matching keywords falls through to plan/build defaults', () => {
    const plan = getScenarioForPrompt('random unrelated prompt', 'plan');
    const build = getScenarioForPrompt('random unrelated prompt', 'build');
    expect(plan.events.length).toBeGreaterThan(0);
    expect(build.events.length).toBeGreaterThan(0);
  });
});

describe('runScenario', () => {
  test('fires onEvent for each event then onComplete', async () => {
    const scenario: Scenario = {
      events: [
        { kind: 'thinking', text: 'a', duration: 10 },
        { kind: 'message', text: 'b' },
      ],
      prompt: 'test',
    };

    const onEvent = vi.fn();
    const onComplete = vi.fn();

    runScenario(scenario, onEvent, onComplete);

    await new Promise((r) => setTimeout(r, 1500));

    expect(onEvent).toHaveBeenCalledTimes(2);
    expect(onEvent).toHaveBeenCalledWith(scenario.events[0], 0);
    expect(onEvent).toHaveBeenCalledWith(scenario.events[1], 1);
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  test('abort stops further events', async () => {
    const scenario: Scenario = {
      events: [
        { kind: 'thinking', text: 'a', duration: 10 },
        { kind: 'message', text: 'b' },
        { kind: 'message', text: 'c' },
      ],
      prompt: 'test',
    };

    const onEvent = vi.fn();
    const onComplete = vi.fn();

    const runner = runScenario(scenario, onEvent, onComplete);
    runner.abort();

    await new Promise((r) => setTimeout(r, 500));

    expect(onEvent).not.toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled();
  });
});
