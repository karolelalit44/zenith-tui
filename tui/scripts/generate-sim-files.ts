import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { collectHrmsBuildEvents } from '../src/services/scenario/hrmsBuildDriver';
import { collectTodoLifecycleEvents } from '../src/services/transport/todoLifecycleEmitter';
import type { ScenarioEvent } from '../src/types/scenario';

const VALID_KINDS = new Set([
  'thinking',
  'message',
  'tool_call',
  'tool_result',
  'error',
  'warning',
  'success',
  'progress',
  'plan_ready',
  'agent_orchestration',
  'context_compacted',
  'context_compaction_started',
  'context_compaction_ended',
  'context_compaction_phase',
  'turn_manifest',
  'todo_board',
  'todo_test',
]);

function toRaw(e: ScenarioEvent): Record<string, unknown> {
  const base: Record<string, unknown> = { kind: e.kind };
  switch (e.kind) {
    case 'thinking': {
      const thoughts = Array.isArray(e.thoughts) ? e.thoughts.map((t) => (typeof t === 'string' ? t : t.text)) : [];
      base.text = thoughts.join(' ');
      base.duration = e.duration;
      return base;
    }
    case 'message': {
      base.text = e.text;
      if (e.partial) base.partial = true;
      if (typeof e.iteration === 'number') base.iteration = e.iteration;
      return base;
    }
    case 'tool_call': {
      base.tool = e.tool;
      base.params = e.params;
      if (e.text) base.text = e.text;
      return base;
    }
    case 'tool_result': {
      base.tool = e.tool;
      base.success = e.success;
      base.output = e.output;
      base.error = e.error;
      if (e.truncated) base.truncated = true;
      base.metadata = e.metadata;
      return base;
    }
    case 'error': {
      base.message = e.message;
      if (e.code) base.code = e.code;
      if (typeof e.recoverable === 'boolean') base.recoverable = e.recoverable;
      if (e.provider) base.provider = e.provider;
      if (e.action) base.action = e.action;
      if (e.hint) base.hint = e.hint;
      return base;
    }
    case 'warning': {
      base.message = e.message;
      if (e.code) base.code = e.code;
      return base;
    }
    case 'success': {
      base.message = e.message;
      if (typeof e.iterations === 'number') base.iterations = e.iterations;
      if (e.tokenInfo) base.tokenInfo = e.tokenInfo;
      if (typeof e.elapsedMs === 'number') base.elapsedMs = e.elapsedMs;
      return base;
    }
    case 'progress': {
      base.label = e.label;
      if (typeof e.percent === 'number') base.percent = e.percent;
      if (typeof e.iteration === 'number') base.iteration = e.iteration;
      base.steps = e.steps;
      return base;
    }
    case 'plan_ready': {
      base.plan = e.plan;
      base.session_id = e.sessionId;
      return base;
    }
    case 'agent_orchestration': {
      base.stage = e.stage;
      base.captainMessage = e.captainMessage;
      if (e.plan) base.plan = e.plan;
      if (e.crewmates) base.crewmates = e.crewmates;
      if (e.timeline) base.timeline = e.timeline;
      if (e.activeStep) base.activeStep = e.activeStep;
      return base;
    }
    case 'context_compacted': {
      if (e.tool) base.tool = e.tool;
      if (typeof e.tokensSaved === 'number') base.tokensSaved = e.tokensSaved;
      return base;
    }
    case 'context_compaction_started': {
      if (typeof e.used === 'number') base.used = e.used;
      if (typeof e.total === 'number') base.total = e.total;
      return base;
    }
    case 'context_compaction_ended': {
      if (typeof e.used === 'number') base.used = e.used;
      if (typeof e.total === 'number') base.total = e.total;
      if (typeof e.tokensSaved === 'number') base.tokensSaved = e.tokensSaved;
      if (typeof e.summaryChars === 'number') base.summaryChars = e.summaryChars;
      if (e.preserved) base.preserved = e.preserved;
      if (e.summary) base.summary = e.summary;
      if (typeof e.failed === 'boolean') base.failed = e.failed;
      return base;
    }
    case 'context_compaction_phase': {
      base.phase = e.phase;
      if (e.label) base.label = e.label;
      if (typeof e.beforeTokens === 'number') base.beforeTokens = e.beforeTokens;
      if (typeof e.afterTokens === 'number') base.afterTokens = e.afterTokens;
      return base;
    }
    case 'turn_manifest': {
      base.created = e.created;
      base.modified = e.modified;
      base.remaining = e.remaining;
      base.completed = e.completed;
      base.stalled = e.stalled;
      base.files = e.files;
      return base;
    }
    case 'todo_board': {
      base.action = e.action;
      base.board = e.board;
      if (e.change) base.change = e.change;
      if (e.message) base.message = e.message;
      return base;
    }
    case 'todo_test': {
      base.phase = e.phase;
      base.scenario = e.scenario;
      base.passed = e.passed;
      base.assertions = e.assertions;
      if (e.rejectedOps) base.rejectedOps = e.rejectedOps;
      if (typeof e.elapsedMs === 'number') base.elapsedMs = e.elapsedMs;
      return base;
    }
    default:
      return base;
  }
}

function buildFile(name: string, match: Record<string, unknown>, events: ScenarioEvent[]): object {
  const rawEvents = events.map(toRaw);
  const invalid = rawEvents.filter((e) => !VALID_KINDS.has(String(e.kind)));
  if (invalid.length > 0) {
    throw new Error(`${name}: invalid server kinds ${invalid.map((e) => e.kind).join(', ')}`);
  }
  return {
    name,
    match,
    mode: 'round_robin',
    responses: [
      {
        reasoning: `Scripted ${name} playback driven from the ${name} driver.`,
        content: '',
        chunk_size: 1,
        delay_ms: 15,
        events: rawEvents,
      },
    ],
  };
}

const simDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../data/simulation');
mkdirSync(simDir, { recursive: true });

const lifecycle = collectTodoLifecycleEvents();
const hrms = collectHrmsBuildEvents();

const todoFile = path.join(simDir, 'todo-lifecycle.json');
const hrmsFile = path.join(simDir, 'hrms-build.json');
writeFileSync(
  todoFile,
  JSON.stringify(buildFile('todo-lifecycle', { contains: 'todo', mode: 'build' }, lifecycle), null, 2) + '\n',
  'utf-8',
);
writeFileSync(
  hrmsFile,
  JSON.stringify(buildFile('hrms-build', { contains: 'hrms', mode: 'build' }, hrms), null, 2) + '\n',
  'utf-8',
);

const kindCount = (events: ScenarioEvent[]) =>
  events.reduce<Record<string, number>>((acc, e) => {
    acc[e.kind] = (acc[e.kind] || 0) + 1;
    return acc;
  }, {});

console.log(`wrote ${todoFile} (${lifecycle.length} events)`);
console.log(kindCount(lifecycle));
console.log(`wrote ${hrmsFile} (${hrms.length} events)`);
console.log(kindCount(hrms));
