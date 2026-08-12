import { Box, Text } from 'ink';
import React, { Component, type ReactNode, useMemo } from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { ScenarioEvent, TurnManifestEvent } from '../../../types/scenario';
import { componentRegistry } from './componentRegistry';

interface ScenarioRendererProps {
  events: ScenarioEvent[];
  isRunning: boolean;
  isHistorical?: boolean;
  thinkingCollapsed?: boolean;
  historyExpanded?: boolean;
  workspaceName?: string;
  gitBranch?: string;
}

export interface LiveBannerState {
  interruptible: boolean;
  hint: string | null;
}

export function resolveLiveBanner(lastEvent: ScenarioEvent | undefined): LiveBannerState {
  if (!lastEvent) return { interruptible: true, hint: 'esc to interrupt' };
  if (lastEvent.kind === 'warning') {
    const code = (lastEvent.code || '').toUpperCase();
    if (code.startsWith('RATE_LIMIT') || code === 'QUOTA') {
      return { interruptible: false, hint: 'waiting for rate limit cooldown…' };
    }
    return { interruptible: true, hint: 'esc to interrupt' };
  }
  if (lastEvent.kind === 'error' || lastEvent.kind === 'success') {
    return { interruptible: false, hint: null };
  }
  return { interruptible: true, hint: 'esc to interrupt' };
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

const EXPLORATORY_TOOLS = new Set([
  'file_read',
  'list_dir',
  'glob',
  'grep',
  'grep_search',
  'get_tool_definition',
  'discover_capabilities',
  'lsp_definition',
  'lsp_diagnostics',
  'webfetch',
  'websearch',
  'todo',
  'job_output',
]);

const MUTATING_TOOLS = new Set([
  'file_write',
  'file_edit',
  'multi_edit',
  'file_delete',
  'bash',
  'execute',
  'run_command',
  'job_kill',
  'lsp_rename',
  'agent',
]);

const TOOL_EVENT_KINDS = new Set(['tool_step', 'tool_call', 'tool_result']);

function isToolEvent(event: ScenarioEvent): boolean {
  return TOOL_EVENT_KINDS.has(event.kind);
}

function phaseLabelFor(tools: string[]): string | null {
  if (tools.some((t) => MUTATING_TOOLS.has(t))) return 'Executing plan…';
  if (tools.length > 0 && tools.some((t) => EXPLORATORY_TOOLS.has(t))) return 'Exploring codebase…';
  return null;
}

function countHiddenEvents(hidden: ScenarioEvent[]): string | null {
  const counts = { reads: 0, writes: 0, searches: 0, commands: 0, other: 0 };
  for (const e of hidden) {
    if (e.kind !== 'tool_step') continue;
    const tool = e.tool;
    if (['file_read', 'list_dir', 'job_output', 'lsp_definition', 'lsp_diagnostics'].includes(tool)) counts.reads++;
    else if (['file_write', 'file_edit', 'multi_edit', 'file_delete', 'lsp_rename'].includes(tool)) counts.writes++;
    else if (['glob', 'grep', 'grep_search', 'websearch'].includes(tool)) counts.searches++;
    else if (['bash', 'execute', 'run_command', 'job_kill'].includes(tool)) counts.commands++;
    else counts.other++;
  }
  const parts: string[] = [];
  if (counts.reads) parts.push(`${counts.reads} read${counts.reads === 1 ? '' : 's'}`);
  if (counts.writes) parts.push(`${counts.writes} write${counts.writes === 1 ? '' : 's'}`);
  if (counts.searches) parts.push(`${counts.searches} search${counts.searches === 1 ? '' : 'es'}`);
  if (counts.commands) parts.push(`${counts.commands} command${counts.commands === 1 ? '' : 's'}`);
  if (counts.other) parts.push(`${counts.other} other`);
  return parts.length > 0 ? parts.join(', ') : null;
}

export const ScenarioRenderer: React.FC<ScenarioRendererProps> = React.memo(
  ({
    events,
    isRunning,
    isHistorical = false,
    thinkingCollapsed = false,
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

    const liveMaxLimit = Math.max(15, rows - 6);
    const visibleEvents = useMemo(() => {
      return events;
    }, [events]);

    const hiddenEvents: ScenarioEvent[] = [];
    const hiddenSummary = null;

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

    const phaseLabels = useMemo(() => {
      const labels = new Map<string, string | null>();
      let lastLabel: string | null = null;
      let i = 0;
      const n = visibleEvents.length;
      while (i < n) {
        if (!isToolEvent(visibleEvents[i])) {
          i++;
          continue;
        }
        const start = i;
        const tools: string[] = [];
        while (i < n && isToolEvent(visibleEvents[i])) {
          const ev = visibleEvents[i];
          if (ev.kind === 'tool_step' || ev.kind === 'tool_call') tools.push(ev.tool);
          i++;
        }
        const label = phaseLabelFor(tools);
        if (label && label !== lastLabel) {
          labels.set(visibleEvents[start].id, label);
        }
        if (label) lastLabel = label;
      }
      return labels;
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

    return (
      <Box flexDirection="column" width="100%">
        {pinnedEarly && renderEvent(pinnedEarly)}

        {hasOverflow && !expanded && (
          <Box paddingX={1} marginBottom={1}>
            <Text color={theme.colors.text.muted} italic>
              ... {events.length - dynamicLimit} earlier events hidden
              {hiddenSummary ? ` (${hiddenSummary})` : ''} — shift+e to show all
            </Text>
          </Box>
        )}

        {visibleEvents.map((event) => {
          const phaseLabel = phaseLabels.get(event.id);
          return (
            <Box key={event.id} flexDirection="column" width="100%">
              {phaseLabel && (
                <Box paddingX={1} marginTop={0} marginBottom={1} width="100%">
                  <Text color={theme.colors.status.info} bold>
                    ◈ {phaseLabel}
                  </Text>
                </Box>
              )}
              {renderEvent(event)}
            </Box>
          );
        })}
      </Box>
    );
  },
);
