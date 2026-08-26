import { Box, Text } from 'ink';
import React, { Component, type ReactNode, useMemo } from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type {
  AgentOrchestrationEvent,
  CrewmateAgent,
  ScenarioEvent,
  TimelineEntry,
  TurnManifestEvent,
} from '../../../types/scenario';
import { consolidateCompactionEvents } from '../../../utils/compaction';
import { consolidateTodoBoardEvents } from '../../../utils/todoBoard';
import { componentRegistry } from './componentRegistry';

interface ScenarioRendererProps {
  events: ScenarioEvent[];
  isRunning: boolean;
  isHistorical?: boolean;
  thinkingCollapsed?: boolean;
  /** /clam — when true, thinking records are never rendered. */
  calmMode?: boolean;
  historyExpanded?: boolean;
  workspaceName?: string;
  gitBranch?: string;
}

class EventErrorBoundary extends Component<
  { children: ReactNode; eventKind: string; errorColor: string },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <Box paddingX={1} marginBottom={1}>
          <Text color={this.props.errorColor}>[Render error in {this.props.eventKind} event — skipped]</Text>
        </Box>
      );
    }
    return this.props.children;
  }
}

export const ScenarioRenderer: React.FC<ScenarioRendererProps> = React.memo(
  ({
    events,
    isRunning,
    isHistorical = false,
    thinkingCollapsed = false,
    calmMode = false,
    historyExpanded = false,
    workspaceName,
    gitBranch,
  }) => {
    const { theme } = useTheme();

    const renderContext = useMemo(
      () => ({
        thinkingCollapsed,
        isHistorical,
        isRunning,
        workspaceName,
        gitBranch,
      }),
      [thinkingCollapsed, isHistorical, isRunning, workspaceName, gitBranch],
    );

    const rows = process.stdout.rows ?? 24;
    const dynamicLimit = Math.max(10, Math.min(20, rows - 8));
    const hasOverflow = !isHistorical && events.length > dynamicLimit;
    const expanded = hasOverflow && historyExpanded;

    const pinnedEarly = useMemo(() => {
      if (!hasOverflow || expanded) return null;
      const firstAssistantMessage = events.find((e) => e.kind === 'message');
      if (!firstAssistantMessage) return null;
      return events.slice(-dynamicLimit).includes(firstAssistantMessage) ? null : firstAssistantMessage;
    }, [events, hasOverflow, expanded, dynamicLimit]);

    const visibleEvents = useMemo(() => {
      // Calm mode (/clam): strip thinking records entirely — not collapsed,
      // simply never rendered.
      const source = calmMode ? events.filter((e) => e.kind !== 'thinking') : events;
      // Consolidate multiple agent_orchestration events into a single stable card
      const orchEvents = source.filter((e): e is AgentOrchestrationEvent => e.kind === 'agent_orchestration');
      let consolidatedOrch: AgentOrchestrationEvent | null = null;
      if (orchEvents.length > 0) {
        const latest = orchEvents[orchEvents.length - 1];
        const crewmatesMap = new Map<string, CrewmateAgent>();
        const timelineEntries: TimelineEntry[] = [];

        // Fold raw sub-agent lifecycle kinds into the card timeline so the
        // crewmate story stays in one place (no standalone rows).
        const rawAgentEntries: TimelineEntry[] = [];
        for (const e of events) {
          if (e.kind === 'agent_spawned') {
            rawAgentEntries.push({
              timestamp: e.id,
              message: `Spawned ${e.name} (${e.role})`,
              type: 'info',
            });
          } else if (e.kind === 'agent_status') {
            if (e.activity) {
              rawAgentEntries.push({ timestamp: e.id, message: e.activity, type: 'info' });
            }
          } else if (e.kind === 'agent_complete') {
            rawAgentEntries.push({
              timestamp: e.id,
              message: e.resultSummary || `${e.agentId} completed`,
              type: 'success',
            });
          } else if (e.kind === 'agent_failed') {
            rawAgentEntries.push({
              timestamp: e.id,
              message: e.error || `${e.agentId} failed`,
              type: 'error',
            });
          }
        }

        for (const oe of orchEvents) {
          if (oe.crewmates) {
            for (const cm of oe.crewmates) {
              crewmatesMap.set(cm.id, cm);
            }
          }
          if (oe.timeline) {
            for (const tl of oe.timeline) {
              if (
                !timelineEntries.some(
                  (existing) => existing.timestamp === tl.timestamp && existing.message === tl.message,
                )
              ) {
                timelineEntries.push(tl);
              }
            }
          }
        }
        for (const tl of rawAgentEntries) {
          if (
            !timelineEntries.some((existing) => existing.timestamp === tl.timestamp && existing.message === tl.message)
          ) {
            timelineEntries.push(tl);
          }
        }

        consolidatedOrch = {
          kind: 'agent_orchestration',
          id: orchEvents[0].id,
          stage: latest.stage,
          captainMessage: latest.captainMessage,
          plan: latest.plan,
          crewmates: crewmatesMap.size > 0 ? Array.from(crewmatesMap.values()) : undefined,
          timeline: timelineEntries.length > 0 ? timelineEntries : undefined,
          activeStep: latest.activeStep,
        };
      }

      const result: ScenarioEvent[] = [];
      let orchInserted = false;
      let compactionInserted = false;
      let boardInserted = false;
      const consolidatedCompaction = consolidateCompactionEvents(events);
      const consolidatedBoard = consolidateTodoBoardEvents(events);

      for (const e of source) {
        if (e.kind === 'agent_orchestration') {
          if (!orchInserted && consolidatedOrch) {
            result.push(consolidatedOrch);
            orchInserted = true;
          }
        } else if (e.kind === 'todo_board') {
          // Fold every board snapshot into ONE minimal window (checkbox + SN +
          // name, capped at 10 rows).
          if (!boardInserted && consolidatedBoard) {
            result.push(consolidatedBoard);
            boardInserted = true;
          }
        } else if (e.kind === 'todo_test') {
          // The assertion/edge-case report is an internal test layer — the
          // rendered todo window shows the board only, so skip these events.
        } else if (
          e.kind === 'agent_spawned' ||
          e.kind === 'agent_status' ||
          e.kind === 'agent_complete' ||
          e.kind === 'agent_failed'
        ) {
          // Raw sub-agent lifecycle kinds are folded into the consolidated
          // orchestration card's timeline above; never render standalone.
        } else if (
          e.kind === 'context_compaction_started' ||
          e.kind === 'context_compaction_phase' ||
          e.kind === 'context_compacted' ||
          e.kind === 'context_compaction_ended'
        ) {
          // Fold all compaction lifecycle events into ONE continuous card.
          if (!compactionInserted && consolidatedCompaction) {
            result.push(consolidatedCompaction);
            compactionInserted = true;
          }
        } else {
          result.push(e);
        }
      }

      const hasSuccess = result.some((e) => e.kind === 'success');
      if (!hasSuccess) {
        return [
          ...result,
          {
            kind: 'success',
            id: isHistorical ? 'evt_historical_status_row' : 'evt_live_status_row',
            elapsedMs: isHistorical ? 1000 : 0,
          } as ScenarioEvent,
        ];
      }
      return result;
    }, [events, calmMode, isHistorical]);

    // The server emits turn_manifest immediately before the success event, so
    // associate each success with the most recent manifest to enrich its line.
    const successManifests = useMemo(() => {
      const map = new Map<string, TurnManifestEvent>();
      let lastManifest: TurnManifestEvent | null = null;
      for (const e of visibleEvents) {
        if (e.kind === 'turn_manifest') lastManifest = e;
        else if (e.kind === 'success' && lastManifest) map.set(e.id, lastManifest);
      }
      return map;
    }, [visibleEvents]);

    const renderEvent = (event: ScenarioEvent) => {
      const Component = componentRegistry.getComponent(event.kind);
      const manifest = event.kind === 'success' ? successManifests.get(event.id) : undefined;
      return (
        <EventErrorBoundary key={event.id} eventKind={event.kind} errorColor={theme.colors.status.warning}>
          <Component event={event} context={renderContext} manifest={manifest} turnEvents={events} />
        </EventErrorBoundary>
      );
    };

    const termCols = process.stdout.columns;
    const contentWidth = termCols ? Math.max(30, termCols - 2) : '100%';

    return (
      <Box flexDirection="column" width={contentWidth}>
        {pinnedEarly && renderEvent(pinnedEarly)}

        {hasOverflow && !expanded && (
          <Box paddingX={1} marginBottom={1}>
            <Text color={theme.colors.text.muted} italic>
              ... {events.length - dynamicLimit} earlier events hidden — shift+e to show all
            </Text>
          </Box>
        )}

        {visibleEvents.map((event) => {
          return (
            <Box key={event.id} flexDirection="column" width={contentWidth}>
              {renderEvent(event)}
            </Box>
          );
        })}
      </Box>
    );
  },
);
