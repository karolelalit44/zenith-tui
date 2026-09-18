import type {
  CaptainOrchestrationEvent,
  CrewmateAgent,
  CrewmateStatus,
  PlanItem,
  ScenarioEvent,
  TimelineEntry,
} from '../types/scenario';

export const MAX_TIMELINE_ENTRIES = 12;

export interface ConsolidatedOrchestration extends CaptainOrchestrationEvent {
  hasFailedCrew: boolean;
  allComplete: boolean;
  activeCrewmateCount: number;
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
      const existing = crewmatesMap.get(id);
      if (existing) {
        existing.status = (e.status as CrewmateStatus) || existing.status;
        if (e.activity) existing.activity = e.activity;
        if (typeof e.progress === 'number') existing.progress = e.progress;
      } else if (id) {
        crewmatesMap.set(id, {
          id,
          name: id,
          role: 'Specialist',
          task: 'Delegated mission',
          status: (e.status as CrewmateStatus) || 'working',
          activity: e.activity,
          progress: e.progress,
        });
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
      const id = e.crewmateId;
      const existing = crewmatesMap.get(id);
      if (existing) {
        existing.status = 'completed';
        existing.progress = 100;
        if (e.resultSummary) existing.resultSummary = e.resultSummary;
      }
      const agentName = existing?.name || id;
      const msg = `${agentName} ✔ ${e.resultSummary || 'Task completed'}`;
      if (!timelineEntries.some((t) => t.message === msg)) {
        timelineEntries.push({
          timestamp: new Date().toISOString(),
          message: msg,
          type: 'success',
        });
      }
    } else if (e.kind === 'crewmate_failed') {
      const id = e.crewmateId;
      const existing = crewmatesMap.get(id);
      if (existing) {
        existing.status = 'failed';
        if (e.error) existing.error = e.error;
      }
      const agentName = existing?.name || id;
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

  const hasFailedCrew = crewmatesList.some((cm) => cm.status === 'failed' || cm.status === 'needs_review');
  const allComplete =
    crewmatesList.length > 0 && crewmatesList.every((cm) => cm.status === 'completed' || cm.status === 'retired');

  const activeCrewmateCount = crewmatesList.filter(
    (cm) => cm.status === 'working' || cm.status === 'assigned' || cm.status === 'spawned',
  ).length;

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
