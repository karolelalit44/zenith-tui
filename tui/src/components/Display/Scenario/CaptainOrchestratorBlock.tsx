import { Box, Text } from 'ink';
import React from 'react';
import { SPINNER_FRAMES } from '../../../constants/animation';
import { useAnimationTick } from '../../../context/AnimationContext';
import { useTerminalDimensions } from '../../../hooks/useTerminalDimensions';
import { useTheme } from '../../../theme/ThemeContext';
import type {
  AgentOrchestrationEvent,
  CrewmateAgent,
  CrewmateStatus,
  PlanItem,
  PlanItemStatus,
} from '../../../types/scenario';

interface CaptainOrchestratorBlockProps {
  event: AgentOrchestrationEvent;
}

/** Render status icon and color for Execution Plan Items. */
function renderPlanStatus(status: PlanItemStatus, themeColors: any) {
  switch (status) {
    case 'queued':
      return { icon: '◌ ', label: 'Queued', color: themeColors.text.dim };
    case 'in_progress':
      return { icon: '⠋ ', label: 'In Progress', color: themeColors.status.info };
    case 'completed':
      return { icon: '✓ ', label: 'Completed', color: themeColors.status.success };
    case 'needs_review':
      return { icon: '🔍 ', label: 'Needs Review', color: themeColors.status.warning };
    case 'failed':
      return { icon: '✗ ', label: 'Failed', color: themeColors.status.error };
    case 'reassigned':
      return { icon: '🔀 ', label: 'Reassigned', color: themeColors.status.accent };
    default:
      return { icon: '• ', label: status, color: themeColors.text.muted };
  }
}

/** Render status icon and color for Crewmate Agents. */
function renderCrewmateStatus(status: CrewmateStatus, themeColors: any, tick: number) {
  switch (status) {
    case 'spawned':
    case 'assigned':
      return { icon: '⚡ ', label: 'Assigned', color: themeColors.status.info };
    case 'working':
      return {
        icon: `${SPINNER_FRAMES[tick % SPINNER_FRAMES.length]} `,
        label: 'Working',
        color: themeColors.status.info,
      };
    case 'returning':
      return { icon: '⬆ ', label: 'Returning', color: themeColors.text.emerald };
    case 'completed':
    case 'reviewed':
      return { icon: '✓ ', label: 'Completed', color: themeColors.status.success };
    case 'needs_review':
      return { icon: '🔍 ', label: 'Reviewing', color: themeColors.status.warning };
    case 'failed':
      return { icon: '✗ ', label: 'Failed', color: themeColors.status.error };
    case 'reassigned':
      return { icon: '🔀 ', label: 'Reassigned', color: themeColors.status.accent };
    case 'retired':
      return { icon: '💤 ', label: 'Retired', color: themeColors.text.dim };
    default:
      return { icon: '• ', label: status, color: themeColors.text.muted };
  }
}

export const CaptainOrchestratorBlock: React.FC<CaptainOrchestratorBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const tick = useAnimationTick();
  const { columns } = useTerminalDimensions();

  const termCols = columns || process.stdout.columns || 80;
  const contentWidth = Math.max(30, termCols - 2);

  const isRunning = event.stage !== 'complete';

  // Format stage label
  let stageLabel = 'Command Center Active';
  let stageColor = theme.colors.status.info;

  switch (event.stage) {
    case 'thinking':
      stageLabel = 'Analyzing Objective';
      stageColor = theme.colors.status.info;
      break;
    case 'planning':
      stageLabel = 'Structuring Execution Plan';
      stageColor = theme.colors.text.emerald;
      break;
    case 'delegating':
      stageLabel = 'Dispatching Crewmate Agents';
      stageColor = theme.colors.status.warning;
      break;
    case 'working':
      stageLabel = 'Parallel Execution Active';
      stageColor = theme.colors.status.info;
      break;
    case 'reviewing':
      stageLabel = 'Evaluating Agent Results';
      stageColor = theme.colors.status.warning;
      break;
    case 'reassigning':
      stageLabel = 'Handling Task Reassignment';
      stageColor = theme.colors.status.accent;
      break;
    case 'synthesizing':
      stageLabel = 'Synthesizing Final Response';
      stageColor = theme.colors.text.emerald;
      break;
    case 'complete':
      stageLabel = 'Orchestration Complete';
      stageColor = theme.colors.status.success;
      break;
  }

  return (
    <Box flexDirection="column" width={contentWidth} marginTop={1} marginBottom={1}>
      <Box
        flexDirection="column"
        backgroundColor={theme.colors.code.background}
        borderStyle="round"
        borderColor={isRunning ? theme.colors.border.active : theme.colors.border.muted}
        paddingX={1}
        paddingY={0}
      >
        {/* Command Center Header Bar */}
        <Box flexDirection="row" alignItems="center" width="100%" flexWrap="nowrap">
          <Box flexDirection="row" alignItems="center" flexGrow={1} flexShrink={1} overflow="hidden">
            <Text color="#FF5F56">● </Text>
            <Text color="#FFBD2E">● </Text>
            <Text color="#27C93F">● </Text>
            <Text color={theme.colors.text.bright} bold wrap="truncate-end">
              ⚡ CAPTAIN ZENITH COMMAND CENTER
            </Text>
            <Text color={theme.colors.text.dim}> · </Text>
            <Text color={stageColor} bold wrap="truncate-end">
              {isRunning ? `${SPINNER_FRAMES[tick % SPINNER_FRAMES.length]} ${stageLabel}` : `✓ ${stageLabel}`}
            </Text>
          </Box>
        </Box>

        {/* Captain Zenith Message Banner */}
        {event.captainMessage ? (
          <Box flexDirection="row" marginTop={0} marginBottom={1}>
            <Text color={theme.colors.status.info} bold>
              Captain Zenith ❯{' '}
            </Text>
            <Text color={theme.colors.text.bright}>{event.captainMessage}</Text>
          </Box>
        ) : null}

        {/* Execution Plan View */}
        {event.plan && event.plan.length > 0 ? (
          <Box flexDirection="column" marginBottom={1} paddingLeft={1}>
            <Box flexDirection="row" marginBottom={0}>
              <Text color={theme.colors.text.emerald} bold>
                📋 EXECUTION PLAN
              </Text>
              <Text color={theme.colors.text.dim}> ({event.plan.length} workstreams)</Text>
            </Box>
            {event.plan.map((item: PlanItem) => {
              const st = renderPlanStatus(item.status, theme.colors);
              return (
                <Box key={item.id} flexDirection="row" alignItems="center" paddingLeft={1}>
                  <Text color={st.color}>{st.icon}</Text>
                  <Text color={item.status === 'completed' ? theme.colors.text.muted : theme.colors.text.bright}>
                    {item.title}
                  </Text>
                  {item.assignedAgent ? <Text color={theme.colors.text.dim}> — {item.assignedAgent}</Text> : null}
                </Box>
              );
            })}
          </Box>
        ) : null}

        {/* Task Dispatch & Parallel Crewmate Cards */}
        {event.crewmates && event.crewmates.length > 0 ? (
          <Box flexDirection="column" marginBottom={1} paddingLeft={1}>
            <Box flexDirection="row" marginBottom={0}>
              <Text color={theme.colors.status.warning} bold>
                👥 CREWMATE SUB-AGENTS DISPATCH
              </Text>
              <Text color={theme.colors.text.dim}>
                {' '}
                ({event.crewmates.length} active worker{event.crewmates.length === 1 ? '' : 's'})
              </Text>
            </Box>

            <Box flexDirection="column" paddingLeft={1}>
              {event.crewmates.map((cm: CrewmateAgent) => {
                const cmSt = renderCrewmateStatus(cm.status, theme.colors, tick);
                return (
                  <Box
                    key={cm.id}
                    flexDirection="column"
                    marginBottom={1}
                    paddingX={1}
                    borderStyle="single"
                    borderColor={cm.status === 'working' ? theme.colors.border.active : theme.colors.border.muted}
                  >
                    {/* Crewmate Header */}
                    <Box flexDirection="row" justifyContent="space-between" alignItems="center">
                      <Box flexDirection="row" alignItems="center">
                        <Text color={theme.colors.status.accent} bold>
                          {cm.name}
                        </Text>
                        <Text color={theme.colors.text.dim}> [{cm.role}]</Text>
                      </Box>
                      <Text color={cmSt.color} bold>
                        {cmSt.icon}
                        {cmSt.label}
                      </Text>
                    </Box>

                    {/* Task details */}
                    <Box flexDirection="row">
                      <Text color={theme.colors.text.dim}>Task: </Text>
                      <Text color={theme.colors.text.bright}>{cm.task}</Text>
                    </Box>

                    {/* Activity subline */}
                    {cm.activity && cm.status === 'working' ? (
                      <Box flexDirection="row">
                        <Text color={theme.colors.text.dim}>Activity: </Text>
                        <Text color={theme.colors.status.info} italic>
                          {cm.activity}
                        </Text>
                      </Box>
                    ) : null}

                    {/* Result Summary */}
                    {cm.resultSummary ? (
                      <Box flexDirection="row">
                        <Text color={theme.colors.status.success}>✓ Result: </Text>
                        <Text color={theme.colors.text.muted}>{cm.resultSummary}</Text>
                      </Box>
                    ) : null}

                    {/* Error message */}
                    {cm.error ? (
                      <Box flexDirection="row">
                        <Text color={theme.colors.status.error}>✗ Error: </Text>
                        <Text color={theme.colors.status.error}>{cm.error}</Text>
                      </Box>
                    ) : null}
                  </Box>
                );
              })}
            </Box>
          </Box>
        ) : null}

        {/* Captain Decision Timeline */}
        {event.timeline && event.timeline.length > 0 ? (
          <Box flexDirection="column" paddingLeft={1} marginBottom={0}>
            <Box flexDirection="row" marginBottom={0}>
              <Text color={theme.colors.status.info} bold>
                ⏱ CAPTAIN DECISION TIMELINE
              </Text>
            </Box>
            {event.timeline.slice(-6).map((tl, idx) => {
              let color = theme.colors.text.dim;
              if (tl.type === 'success') color = theme.colors.status.success;
              if (tl.type === 'warning' || tl.type === 'reassign') color = theme.colors.status.warning;
              if (tl.type === 'error') color = theme.colors.status.error;
              return (
                <Box key={idx} flexDirection="row" paddingLeft={1}>
                  <Text color={theme.colors.text.dim}>{tl.timestamp} </Text>
                  <Text color={theme.colors.text.dim}>│ </Text>
                  <Text color={color}>{tl.message}</Text>
                </Box>
              );
            })}
          </Box>
        ) : null}
      </Box>
    </Box>
  );
});

CaptainOrchestratorBlock.displayName = 'CaptainOrchestratorBlock';
