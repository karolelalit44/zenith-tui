import type { ScenarioEvent } from '../../types/scenario';
import { runTodoLifecycle } from '../todo/todoLifecycleDriver';

/**
 * The todo & subtask lifecycle simulation: a pure TodoStore is driven through
 * Create → Manage → Update → Progress → Complete → Reopen → Persist, persisting
 * the board and reloading it into a fresh store to prove it survives a refresh.
 *
 * In the running app this is triggered by a prompt (e.g. "todo lifecycle")
 * matching the scripted `data/simulation/todo-lifecycle.json` playback on the
 * `/ws/test` backend. `collectTodoLifecycleEvents` is the single source of
 * truth for the event stream: the generator that writes that JSON file, and
 * the frontend test suite, both consume it.
 *
 * The persist phase writes the board snapshot to `data/simulation/todo-board.json`
 * (see `todoPersistence.ts`), alongside the scripted playback files.
 */

/**
 * Compute the full typed event stream up front (no timing). Handy for tests
 * and for pre-computing the board states.
 */
export function collectTodoLifecycleEvents(options?: { outputDir?: string }): ScenarioEvent[] {
  return runTodoLifecycle({ outputDir: options?.outputDir }).events;
}
