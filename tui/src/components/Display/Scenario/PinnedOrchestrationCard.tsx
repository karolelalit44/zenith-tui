import { Box, Text } from 'ink';
import React from 'react';
import { SPINNER_FRAMES } from '../../../constants/animation';
import { contentWidth as computeContentWidth } from '../../../constants/layout';
import { useAnimationTick } from '../../../context/AnimationContext';
import { useTerminalDimensions } from '../../../hooks/useTerminalDimensions';
import { useTheme } from '../../../theme/ThemeContext';
import type { CrewmateAgent, CrewmateStatus, TimelineEntry } from '../../../types/scenario';
import type { ConsolidatedOrchestration } from '../../../utils/orchestration';

interface PinnedOrchestrationCardProps {
  event: ConsolidatedOrchestration;
  isRunning?: boolean;
}

const LiveSpinner: React.FC = () => {
  const tick = useAnimationTick();
  return <>{SPINNER_FRAMES[tick % SPINNER_FRAMES.length]}</>;
};

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

    const renderCrewmateBadge = (status: CrewmateStatus) => {
      switch (status) {
        case 'completed':
        case 'reviewed':
          return (
            <Text color={colors.status.success} bold>
              ✔ DONE
            </Text>
          );
        case 'working':
          return (
            <Text color={colors.status.info} bold>
              {isMissionRunning ? <LiveSpinner /> : '◐'} ACTIVE
            </Text>
          );
        case 'failed':
          return (
            <Text color={colors.status.error} bold>
              ✖ FAILED
            </Text>
          );
        case 'retired':
          return <Text color={colors.text.dim}>○ RETIRED</Text>;
        default:
          return <Text color={colors.status.info}>⚡ READY</Text>;
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
        {/* Header row: Traffic Lights + Title + Stage status + Crewmate count */}
        <Box flexDirection="row" width="100%" justifyContent="space-between" alignItems="center">
          <Box flexDirection="row" alignItems="center" flexShrink={0}>
            <Text color={colors.decorative.trafficLight.red}>● </Text>
            <Text color={colors.decorative.trafficLight.yellow}>● </Text>
            <Text color={colors.decorative.trafficLight.green}>● </Text>
            <Text color={colors.text.bright} bold>
              ⚡ Captain{' '}
            </Text>
            <Text color={colors.text.dim}>({crewmates.length} crew) </Text>
            <Text
              color={
                isMissionRunning
                  ? colors.status.info
                  : event.hasFailedCrew
                    ? colors.status.error
                    : colors.status.success
              }
              bold
            >
              {isMissionRunning ? (
                <>
                  <LiveSpinner /> {stageLabel}
                </>
              ) : event.hasFailedCrew ? (
                '✗ Failed'
              ) : (
                '✔ Complete'
              )}
            </Text>
          </Box>

          {/* Right-aligned directive ticker */}
          {event.activeStep ? (
            <Box flexDirection="row" alignItems="center" flexShrink={1} marginLeft={1}>
              <Text color={colors.status.accent} bold>
                ↳{' '}
              </Text>
              <Text color={colors.text.bright} wrap="truncate-end">
                {event.activeStep}
              </Text>
            </Box>
          ) : event.captainMessage ? (
            <Box flexDirection="row" alignItems="center" flexShrink={1} marginLeft={1}>
              <Text color={colors.text.muted} wrap="truncate-end">
                {event.captainMessage}
              </Text>
            </Box>
          ) : null}
        </Box>

        {/* Crewmates detail rows */}
        {crewmates.length > 0 && (
          <Box flexDirection="column" marginTop={0}>
            {crewmates.map((cm: CrewmateAgent) => (
              <Box key={cm.id} flexDirection="column" width="100%">
                <Box flexDirection="row" width="100%" alignItems="center">
                  <Box width={10} flexShrink={0}>
                    {renderCrewmateBadge(cm.status)}
                  </Box>
                  <Box flexShrink={0} marginRight={1}>
                    <Text color={colors.status.accent} bold>
                      {cm.name}
                    </Text>
                    <Text color={colors.text.dim}> [{cm.role}]</Text>
                  </Box>
                  <Box flexGrow={1} flexShrink={1}>
                    <Text
                      color={cm.status === 'completed' ? colors.text.muted : colors.text.bright}
                      wrap="truncate-end"
                    >
                      {cm.task}
                    </Text>
                  </Box>
                </Box>

                {/* In-flight activity subline */}
                {cm.activity && cm.status === 'working' && (
                  <Box flexDirection="row" paddingLeft={2}>
                    <Text color={colors.status.accent}>↳ </Text>
                    <Text color={colors.status.info}>
                      <LiveSpinner />{' '}
                    </Text>
                    <Text color={colors.text.bright} italic wrap="truncate-end">
                      {cm.activity}
                    </Text>
                  </Box>
                )}

                {/* Result summary */}
                {cm.resultSummary && (
                  <Box flexDirection="row" paddingLeft={2}>
                    <Text color={colors.status.success}>✔ Result: </Text>
                    <Text color={colors.text.muted} wrap="truncate-end">
                      {cm.resultSummary}
                    </Text>
                  </Box>
                )}

                {/* Error message */}
                {cm.error && (
                  <Box flexDirection="row" paddingLeft={2}>
                    <Text color={colors.status.error}>✗ Error: </Text>
                    <Text color={colors.status.error} wrap="truncate-end">
                      {cm.error}
                    </Text>
                  </Box>
                )}
              </Box>
            ))}
          </Box>
        )}

        {/* Real-time Agent Communication Timeline (latest 3 events) */}
        {event.timeline && event.timeline.length > 0 && (
          <Box flexDirection="column" marginTop={0} paddingTop={0}>
            <Box flexDirection="row">
              <Text color={colors.text.dim}>── Communication Stream ──</Text>
            </Box>
            {event.timeline.slice(-3).map((tl: TimelineEntry, idx: number) => {
              let msgColor = colors.text.dim;
              if (tl.type === 'success') msgColor = colors.status.success;
              else if (tl.type === 'warning') msgColor = colors.status.warning;
              else if (tl.type === 'error') msgColor = colors.status.error;
              else if (tl.type === 'info') msgColor = colors.text.bright;

              const timeDisplay = tl.timestamp.includes('T')
                ? tl.timestamp.split('T')[1]?.slice(0, 8)
                : tl.timestamp.slice(0, 8);

              return (
                <Box key={idx} flexDirection="row" paddingLeft={1}>
                  <Text color={colors.text.dim}>{timeDisplay || '··:··:··'} </Text>
                  <Text color={colors.text.dim}>│ </Text>
                  <Text color={msgColor} wrap="truncate-end">
                    {tl.message}
                  </Text>
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
