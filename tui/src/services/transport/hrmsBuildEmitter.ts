import type { ScenarioEvent } from '../../types/scenario';
import { runHrmsBuildSimulation } from '../scenario/hrmsBuildDriver';

/**
 * The long Django HRMS build simulation: captain + crewmates, todo board, tool
 * steps (incl. failure + recovery), context compaction, turn manifest, and
 * success — exercising every scenario event kind end to end.
 *
 * In the running app this is triggered by a prompt (e.g. "build the hrms
 * django app") matching the scripted `data/simulation/hrms-build.json`
 * playback on the `/ws/test` backend. `collectHrmsBuildEvents` is the single
 * source of truth for the event stream: the generator that writes that JSON
 * file, and the frontend test suite, both consume it.
 */

/**
 * Compute the full typed event stream up front (no timing).
 */
export function collectHrmsBuildEvents(): ScenarioEvent[] {
  return runHrmsBuildSimulation().events;
}
