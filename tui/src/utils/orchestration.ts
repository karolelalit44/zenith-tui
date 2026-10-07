import type {
  CaptainOrchestrationEvent,
  CrewmateAgent,
  CrewmateStatus,
  PlanItem,
  ScenarioEvent,
  TimelineEntry,
} from '../types/scenario';

type Crewmate = CrewmateAgent;

export const MAX_TIMELINE_ENTRIES = 12;

export interface ConsolidatedOrchestration extends CaptainOrchestrationEvent {
  hasFailedCrew: boolean;
  allComplete: boolean;
  activeCrewmateCount: number;
}

/**
 * The status buckets the server actually emits.
 *
 * `CREWMATE_STATUS_BY_RESULT` (server/agents/delegation/orchestrator.py) plus the
 * "assigned"/"working" literals are the whole vocabulary: completed, failed,
 * retired, assigned, working. Narrowing the type here means a status the server
 * cannot send becomes a compile error instead of a permanently false branch.
 */
export type EmittableCrewmateStatus = Extract<
  CrewmateStatus,
  'completed' | 'failed' | 'retired' | 'assigned' | 'working'
>;

const TERMINAL_STATUSES: ReadonlySet<EmittableCrewmateStatus> = new Set<EmittableCrewmateStatus>([
  'completed',
  'retired',
]);
const ACTIVE_STATUSES: ReadonlySet<EmittableCrewmateStatus> = new Set<EmittableCrewmateStatus>(['assigned', 'working']);
const FAILED_STATUSES: ReadonlySet<EmittableCrewmateStatus> = new Set<EmittableCrewmateStatus>(['failed']);

export interface OrchestrationFlags {
  hasFailedCrew: boolean;
  allComplete: boolean;
  activeCrewmateCount: number;
}

/** The one place mission tallies are derived, so cards cannot disagree about them. */
export function deriveOrchestrationFlags(crewmates: Crewmate[]): OrchestrationFlags {
  const statusOf = (cm: Crewmate): EmittableCrewmateStatus | null => {
    const s = cm.status;
    return s === 'completed' || s === 'failed' || s === 'retired' || s === 'assigned' || s === 'working' ? s : null;
  };
  const seen = crewmates.map(statusOf).filter((s): s is EmittableCrewmateStatus => s !== null);
  return {
    hasFailedCrew: seen.some((s) => FAILED_STATUSES.has(s)),
    allComplete: seen.length > 0 && seen.every((s) => TERMINAL_STATUSES.has(s)),
    activeCrewmateCount: seen.filter((s) => ACTIVE_STATUSES.has(s)).length,
  };
}

/**
 * Consolidate all captain orchestration and crewmate lifecycle events
 * into a single unified orchestration state.
 *
 * Prevents UI jitter by folding raw `crewmate_spawned`, `crewmate_status`,
 * `crewmate_complete`, and `crewmate_failed` events into their respective
 * crewmate agent records and communication timeline.
 */
export function consolidateOrchestrationEvents(events: ScenarioEvent[]): ConsolidatedOrchestration | null {
  if (!events || events.length === 0) return null;

  const orchEvents = events.filter((e): e is CaptainOrchestrationEvent => e.kind === 'captain_orchestration');

  const crewmateEvents = events.filter(
    (e) =>
      e.kind === 'crewmate_spawned' ||
      e.kind === 'crewmate_status' ||
      e.kind === 'crewmate_complete' ||
      e.kind === 'crewmate_failed',
  );

  // Check if explore tool is in flight. The TUI folds tool_call events into
  // pending tool_step entries (useScenario.handleEvent), so a resolved explore
  // appears as a non-pending tool_step. Only the LAST explore step decides: a
  // finished mission with no orchestration snapshot (e.g. hard timeout) must
  // NOT keep a fabricated "working" card alive forever.
  let lastExploreStep: { kind: string; params?: Record<string, unknown>; pending?: boolean } | undefined;
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.kind !== 'tool_step' && e.kind !== 'tool_call') continue;
    if (e.tool !== 'explore') continue;
    lastExploreStep = {
      kind: e.kind,
      params: e.params,
      pending: 'pending' in e ? e.pending : undefined,
    };
    break;
  }
  const exploreInFlight = lastExploreStep
    ? lastExploreStep.kind === 'tool_call' || lastExploreStep.pending === true
    : false;

  if (orchEvents.length === 0 && crewmateEvents.length === 0 && !exploreInFlight) {
    return null;
  }

  const crewmatesMap = new Map<string, CrewmateAgent>();
  const timelineEntries: TimelineEntry[] = [];
  const planMap = new Map<string, PlanItem>();

  // 1. Ingest explicit captain_orchestration events first
  for (const oe of orchEvents) {
    if (oe.plan) {
      for (const item of oe.plan) {
        planMap.set(item.id, item);
      }
    }
    if (oe.crewmates) {
      for (const cm of oe.crewmates) {
        crewmatesMap.set(cm.id, { ...cm });
      }
    }
    if (oe.timeline) {
      for (const tl of oe.timeline) {
        if (!timelineEntries.some((t) => t.timestamp === tl.timestamp && t.message === tl.message)) {
          timelineEntries.push({ ...tl });
        }
      }
    }
  }

  // 2. Fold raw crewmate events into crewmate states and timeline
  //
  // Every lifecycle branch below goes through upsertCrewmate so a status,
  // complete or failed event always lands on a row. The id format has changed
  // once already (bare definition id -> "<definition>:<task8>"), and a persisted
  // session can straddle that change; if only some branches adopted an unknown
  // id, the straddling session produced exactly the phantom rows the composite
  // id was introduced to remove — a timeline entry for a mission with no card,
  // or a card frozen at "working" because its completion went nowhere.
  const upsertCrewmate = (id: string | undefined, seed: Partial<Crewmate> & { status: CrewmateStatus }) => {
    if (!id) return undefined;
    const existing = crewmatesMap.get(id);
    if (existing) {
      Object.assign(existing, seed);
      return existing;
    }
    const created: Crewmate = {
      name: id,
      role: 'Specialist',
      task: 'Delegated mission',
      ...seed,
      id,
    };
    crewmatesMap.set(id, created);
    return created;
  };

  for (const e of events) {
    if (e.kind === 'crewmate_spawned') {
      const id = e.crewmateId || `cm_${e.id}`;
      const existing = crewmatesMap.get(id);
      crewmatesMap.set(id, {
        id,
        name: e.name || 'Crewmate',
        role: e.role || 'Specialist',
        task: existing?.task || e.capability || 'Delegated mission',
        status: existing?.status || 'assigned',
        activity: existing?.activity,
        progress: existing?.progress ?? 0,
      });

      const msg = `Spawned ${e.name || 'Crewmate'} (${e.role || 'Specialist'})`;
      if (!timelineEntries.some((t) => t.message === msg)) {
        timelineEntries.push({
          timestamp: new Date().toISOString(),
          message: msg,
          type: 'info',
        });
      }
    } else if (e.kind === 'crewmate_status') {
      const id = e.crewmateId;
      const existing =
        crewmatesMap.get(id ?? '') ?? upsertCrewmate(id, { status: (e.status as CrewmateStatus) || 'working' });
      if (existing) {
        existing.status = (e.status as CrewmateStatus) || existing.status;
        if (e.activity) existing.activity = e.activity;
        if (typeof e.progress === 'number') existing.progress = e.progress;
      }

      if (e.activity) {
        const agentName = existing?.name || id;
        const msg = `${agentName} ❯ ${e.activity}`;
        if (!timelineEntries.some((t) => t.message === msg)) {
          timelineEntries.push({
            timestamp: new Date().toISOString(),
            message: msg,
            type: 'info',
          });
        }
      }
    } else if (e.kind === 'crewmate_complete') {
      const existing = upsertCrewmate(e.crewmateId, { status: 'completed', progress: 100 });
      if (existing && e.resultSummary) existing.resultSummary = e.resultSummary;
      const agentName = existing?.name || e.crewmateId;
      const msg = `${agentName} ✔ ${e.resultSummary || 'Task completed'}`;
      if (!timelineEntries.some((t) => t.message === msg)) {
        timelineEntries.push({
          timestamp: new Date().toISOString(),
          message: msg,
          type: 'success',
        });
      }
    } else if (e.kind === 'crewmate_failed') {
      const existing = upsertCrewmate(e.crewmateId, { status: 'failed' });
      if (existing && e.error) existing.error = e.error;
      const agentName = existing?.name || e.crewmateId;
      const msg = `${agentName} ✗ ${e.error || 'Mission failed'}`;
      if (!timelineEntries.some((t) => t.message === msg)) {
        timelineEntries.push({
          timestamp: new Date().toISOString(),
          message: msg,
          type: 'error',
        });
      }
    }
  }

  // 3. Fallback for in-flight explore tool without explicit orchestration events.
  //    Truthfully derived from the real tool params (crewmate is a nested
  //    object in the explore schema), never fabricated. No fake progress or
  //    made-up activity; the card stays generic until the server snapshot lands.
  if (crewmatesMap.size === 0 && exploreInFlight && lastExploreStep) {
    const rawParams = lastExploreStep.params || {};
    const crewParam = (rawParams.crewmate as Record<string, unknown> | undefined) || {};
    const objective = rawParams.objective ? String(rawParams.objective) : 'Codebase investigation';
    const name = crewParam.name ? String(crewParam.name) : 'Delegated agent';
    const role = crewParam.role ? String(crewParam.role) : 'Specialist';
    const model = crewParam.model ? String(crewParam.model) : '';
    const id = model ? `${name}:${role}:${model}` : `${name}:${role}`;

    crewmatesMap.set(id, {
      id,
      name,
      role,
      task: objective,
      status: 'working',
    });

    timelineEntries.push({
      timestamp: new Date().toISOString(),
      message: `Captain Zenith ❯ Dispatched ${name} (${role}) to investigate: ${objective}`,
      type: 'info',
    });
  }

  const latestOrch = orchEvents.length > 0 ? orchEvents[orchEvents.length - 1] : null;
  const crewmatesList = Array.from(crewmatesMap.values());

  const { hasFailedCrew, allComplete, activeCrewmateCount } = deriveOrchestrationFlags(crewmatesList);

  let derivedStage: CaptainOrchestrationEvent['stage'] = latestOrch?.stage || 'working';
  if (!latestOrch) {
    derivedStage = allComplete ? 'complete' : 'working';
  }

  // Bounded timeline
  const dedupedTimeline: TimelineEntry[] = [];
  for (const tl of timelineEntries) {
    const prev = dedupedTimeline[dedupedTimeline.length - 1];
    if (prev && prev.message === tl.message) continue;
    dedupedTimeline.push(tl);
  }
  const boundedTimeline = dedupedTimeline.slice(-MAX_TIMELINE_ENTRIES);

  return {
    kind: 'captain_orchestration',
    id: latestOrch?.id || (crewmateEvents[0]?.id ?? 'orch_consolidated'),
    stage: derivedStage,
    captainMessage:
      latestOrch?.captainMessage ||
      (derivedStage === 'complete' ? 'Orchestration mission finished' : 'Captain Zenith dispatching specialists'),
    plan: planMap.size > 0 ? Array.from(planMap.values()) : latestOrch?.plan,
    crewmates: crewmatesList.length > 0 ? crewmatesList : undefined,
    timeline: boundedTimeline.length > 0 ? boundedTimeline : undefined,
    activeStep: latestOrch?.activeStep,
    hasFailedCrew,
    allComplete,
    activeCrewmateCount,
  };
}
