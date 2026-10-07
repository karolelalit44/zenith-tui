import { Box, Text } from 'ink';
import React from 'react';
import { contentWidth as computeContentWidth } from '../../../constants/layout';
import { useTerminalDimensions } from '../../../hooks/useTerminalDimensions';
import { useTheme } from '../../../theme/ThemeContext';
import type { CrewmateAgent, CrewmateStatus, TimelineEntry } from '../../../types/scenario';
import { type ConsolidatedOrchestration, deriveOrchestrationFlags } from '../../../utils/orchestration';
import { Spinner } from '../../ui/Spinner';

/** The pinned card is a summary, not a roster: cap both lists it renders. */
const MAX_VISIBLE_CREWMATES = 4;
const MAX_VISIBLE_TIMELINE = 2;
const UNKNOWN_TIME = '--:--';

interface PinnedOrchestrationCardProps {
  event: ConsolidatedOrchestration;
  isRunning?: boolean;
}

function getStageLabel(stage: string): string {
  switch (stage) {
    case 'thinking':
      return 'Analyzing Objective';
    case 'planning':
      return 'Structuring Plan';
    case 'delegating':
      return 'Dispatching Crew';
    case 'working':
      return 'Execution Active';
    case 'reviewing':
      return 'Reviewing Results';
    case 'reassigning':
      return 'Reassigning Tasks';
    case 'synthesizing':
      return 'Synthesizing Output';
    case 'complete':
      return 'Mission Complete';
    default:
      return stage;
  }
}

function formatTimelineTime(timestamp: string): string {
  if (!timestamp) return UNKNOWN_TIME;
  if (timestamp.includes('T')) return timestamp.split('T')[1]?.slice(0, 5) || UNKNOWN_TIME;
  return timestamp.slice(0, 5) || UNKNOWN_TIME;
}

/**
 * Strip the actor prefix that `consolidateOrchestrationEvents` bakes into each
 * timeline message. Persisted sessions hold the old prefixed string shape, so
 * this stays as a read-side fallback until every stored entry is structured.
 */
function cleanTimelineMessage(message: string): string {
  return message
    .replace(/^Captain Zenith\s*❯\s*/i, '')
    .replace(/^[^\s]+\s*[❯✔✗]\s*/u, '')
    .replace(/\s+/g, ' ')
    .trim();
}

export const PinnedOrchestrationCard: React.FC<PinnedOrchestrationCardProps> = React.memo(
  ({ event, isRunning = false }) => {
    const { theme } = useTheme();
    const colors = theme.colors;
    const { columns } = useTerminalDimensions();
    const termCols = columns || process.stdout.columns || 80;
    const contentWidth = computeContentWidth(termCols);

    const crewmates = event.crewmates ?? [];
    const isMissionRunning = isRunning && event.stage !== 'complete';
    const stageLabel = getStageLabel(event.stage);
    const { activeCrewmateCount: activeCount } = deriveOrchestrationFlags(crewmates);
    const failedCount = crewmates.filter((crewmate) => crewmate.status === 'failed').length;
    const completedCount = crewmates.filter((crewmate) => crewmate.status === 'completed').length;
    const hasSuccessCrew = completedCount > 0;
    // `active_step` is usually free-text in-flight activity ("Reading tools.py"),
    // which is the most useful thing on this line. It is sometimes a state token
    // instead ("complete"/"thinking"/"delegating"), and those are already spoken
    // for by the stage label in the header — promoting one made the objective
    // line read "↳ delegating". Fall back to the captain's message in that case.
    const stepIsStateToken =
      Boolean(event.activeStep) && (event.activeStep === event.stage || event.activeStep === stageLabel);
    const objective = (!stepIsStateToken && event.activeStep) || event.captainMessage || '';
    const visibleCrewmates = crewmates.slice(0, MAX_VISIBLE_CREWMATES);
    const hiddenCrewmates = Math.max(0, crewmates.length - visibleCrewmates.length);
    const timeline = (event.timeline ?? []).slice(-MAX_VISIBLE_TIMELINE);

    const renderCrewStatus = (status: CrewmateStatus) => {
      switch (status) {
        case 'completed':
          return (
            <Text color={colors.status.success} bold>
              ✓ done
            </Text>
          );
        case 'working':
          return (
            <Text color={colors.status.info} bold>
              {isMissionRunning ? <Spinner /> : '◐'} active
            </Text>
          );
        case 'failed':
          return (
            <Text color={colors.status.error} bold>
              ✗ failed
            </Text>
          );
        case 'retired':
          return <Text color={colors.text.dim}>○ retired</Text>;
        default:
          return <Text color={colors.status.info}>◇ ready</Text>;
      }
    };

    return (
      <Box
        flexDirection="column"
        width={contentWidth}
        backgroundColor={colors.code.background}
        borderStyle="round"
        borderColor={isMissionRunning ? colors.border.active : colors.border.muted}
        paddingX={1}
        paddingY={0}
      >
        <Box flexDirection="row" width="100%" alignItems="center" flexWrap="nowrap">
          <Box flexDirection="row" alignItems="center" flexGrow={1} flexShrink={1} overflow="hidden">
            <Text color={colors.text.bright} bold>
              Captain
            </Text>
            <Text color={colors.text.dim}> · </Text>
            <Text
              color={
                isMissionRunning
                  ? colors.status.info
                  : event.hasFailedCrew
                    ? colors.status.error
                    : colors.status.success
              }
              bold
              wrap="truncate-end"
            >
              {isMissionRunning ? (
                <>
                  <Spinner /> {stageLabel}
                </>
              ) : event.hasFailedCrew ? (
                hasSuccessCrew ? (
                  'Partial completion'
                ) : (
                  'Failed'
                )
              ) : (
                'Complete'
              )}
            </Text>
          </Box>
          <Box flexShrink={0} marginLeft={1}>
            <Text color={colors.text.dim}>
              {completedCount}/{crewmates.length || 0} done
            </Text>
            {activeCount > 0 ? <Text color={colors.status.info}> · {activeCount} active</Text> : null}
            {failedCount > 0 ? <Text color={colors.status.error}> · {failedCount} failed</Text> : null}
          </Box>
        </Box>

        {(objective || event.activeStep) && (
          <Box flexDirection="row" width="100%" paddingLeft={1} marginTop={0}>
            <Text color={colors.status.accent}>↳ </Text>
            <Box flexGrow={1} flexShrink={1} overflow="hidden">
              <Text color={colors.text.muted} wrap="truncate-end">
                {objective}
              </Text>
            </Box>
          </Box>
        )}

        {visibleCrewmates.length > 0 && (
          <Box flexDirection="column" marginTop={0}>
            {visibleCrewmates.map((crewmate: CrewmateAgent) => (
              <Box key={crewmate.id} flexDirection="column" width="100%" marginTop={0}>
                <Box flexDirection="row" width="100%" alignItems="center" flexWrap="nowrap">
                  <Box width={9} flexShrink={0}>
                    {renderCrewStatus(crewmate.status)}
                  </Box>
                  <Box flexShrink={0} marginRight={1}>
                    <Text color={colors.text.bright} bold>
                      {crewmate.name}
                    </Text>
                    <Text color={colors.text.dim}> · {crewmate.role}</Text>
                  </Box>
                  <Box flexGrow={1} flexShrink={1} overflow="hidden">
                    <Text color={colors.text.muted} wrap="truncate-end">
                      {crewmate.task}
                    </Text>
                  </Box>
                </Box>

                {crewmate.activity && crewmate.status === 'working' && (
                  <Box flexDirection="row" paddingLeft={2} width="100%">
                    <Text color={colors.status.info}>↳ </Text>
                    <Box flexGrow={1} flexShrink={1} overflow="hidden">
                      <Text color={colors.text.bright} italic wrap="truncate-end">
                        {crewmate.activity}
                      </Text>
                    </Box>
                  </Box>
                )}

                {crewmate.resultSummary && (
                  <Box flexDirection="row" paddingLeft={2} width="100%">
                    <Text color={colors.status.success}>result </Text>
                    <Box flexGrow={1} flexShrink={1} overflow="hidden">
                      <Text color={colors.text.muted} wrap="truncate-end">
                        {crewmate.resultSummary}
                      </Text>
                    </Box>
                  </Box>
                )}

                {crewmate.error && (
                  <Box flexDirection="row" paddingLeft={2} width="100%">
                    <Text color={colors.status.error}>error </Text>
                    <Box flexGrow={1} flexShrink={1} overflow="hidden">
                      <Text color={colors.status.error} wrap="truncate-end">
                        {crewmate.error}
                      </Text>
                    </Box>
                  </Box>
                )}
              </Box>
            ))}
            {hiddenCrewmates > 0 && (
              <Text color={colors.text.dim}>
                +{hiddenCrewmates} more delegated agent{hiddenCrewmates === 1 ? '' : 's'}
              </Text>
            )}
          </Box>
        )}

        {timeline.length > 0 && (
          <Box flexDirection="column" marginTop={0} paddingTop={0}>
            <Text color={colors.text.dim}>Signals</Text>
            {timeline.map((timelineEntry: TimelineEntry, index: number) => {
              let messageColor = colors.text.dim;
              if (timelineEntry.type === 'success') messageColor = colors.status.success;
              else if (timelineEntry.type === 'warning') messageColor = colors.status.warning;
              else if (timelineEntry.type === 'error') messageColor = colors.status.error;
              else if (timelineEntry.type === 'info') messageColor = colors.text.bright;

              return (
                <Box key={`${timelineEntry.timestamp}_${index}`} flexDirection="row" paddingLeft={1} width="100%">
                  <Box width={6} flexShrink={0}>
                    <Text color={colors.text.dim}>{formatTimelineTime(timelineEntry.timestamp)}</Text>
                  </Box>
                  <Box flexGrow={1} flexShrink={1} overflow="hidden">
                    <Text color={messageColor} wrap="truncate-end">
                      {cleanTimelineMessage(timelineEntry.message)}
                    </Text>
                  </Box>
                </Box>
              );
            })}
          </Box>
        )}
      </Box>
    );
  },
);

PinnedOrchestrationCard.displayName = 'PinnedOrchestrationCard';
