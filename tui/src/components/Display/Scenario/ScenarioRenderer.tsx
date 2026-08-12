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

    const visibleEvents = useMemo(() => {
      return events;
    }, [events]);

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

    return (
      <Box flexDirection="column" width="100%">
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
            <Box key={event.id} flexDirection="column" width="100%">
              {renderEvent(event)}
            </Box>
          );
        })}
      </Box>
    );
  },
);
