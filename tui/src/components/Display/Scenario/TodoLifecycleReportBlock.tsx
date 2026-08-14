import { Box, Text } from 'ink';
import React from 'react';
import { SPINNER_FRAMES } from '../../../constants/animation';
import { useAnimationTick } from '../../../context/AnimationContext';
import { useTheme } from '../../../theme/ThemeContext';
import type { TodoLifecyclePhase } from '../../../types/scenario';
import type { ConsolidatedTodoReport } from '../../../utils/todoLifecycle';
import { LIFECYCLE_LABEL, reportPercent } from '../../../utils/todoLifecycle';
import type { EventRenderContext } from './componentRegistry';

interface TodoLifecycleReportBlockProps {
  event: ConsolidatedTodoReport;
  context?: EventRenderContext;
}

const BAR_WIDTH = 20;

function phaseState(_phase: TodoLifecyclePhase, stepIndex: number, allDone: boolean, colors: Record<string, any>) {
  const index = stepIndex;
  if (allDone) {
    return { icon: '✓ ', color: colors.status.success };
  }
  if (index < stepIndex) {
    return { icon: '✓ ', color: colors.status.success };
  }
  if (index === stepIndex) {
    return { icon: `${SPINNER_FRAMES[0]} `, color: colors.status.info };
  }
  return { icon: '○ ', color: colors.text.dim };
}

function assertionColor(passed: boolean, colors: Record<string, any>): string {
  return passed ? colors.status.success : colors.status.error;
}

export const TodoLifecycleReportBlock: React.FC<TodoLifecycleReportBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const colors = theme.colors;
  const tick = useAnimationTick();

  const percent = reportPercent(event);
  const filled = Math.round(BAR_WIDTH * (percent / 100));
  const allDone = event.assertions.length > 0 && event.assertions.every((a) => a.passed);

  return (
    <Box flexDirection="column" width="100%" marginTop={1} marginBottom={1}>
      <Box
        flexDirection="column"
        backgroundColor={colors.code.background}
        borderStyle="round"
        borderColor={allDone ? colors.border.active : colors.border.muted}
        paddingX={1}
        paddingY={0}
      >
        {/* Header bar */}
        <Box flexDirection="row" alignItems="center" width="100%" flexWrap="nowrap">
          <Box flexDirection="row" alignItems="center" flexGrow={1} flexShrink={1} overflow="hidden">
            <Text color="#FF5F56">● </Text>
            <Text color="#FFBD2E">● </Text>
            <Text color="#27C93F">● </Text>
            <Text color={colors.text.bright} bold wrap="truncate-end">
              🧪 TODO SIMULATION
            </Text>
            <Text color={colors.text.dim}> · </Text>
            <Text color={allDone ? colors.status.success : colors.status.info} bold wrap="truncate-end">
              {allDone ? '✓ ALL SCENARIOS PASSED' : `${SPINNER_FRAMES[tick % SPINNER_FRAMES.length]} RUNNING`}
            </Text>
          </Box>
          <Box flexDirection="row" alignItems="center">
            <Text color={colors.status.success} bold>
              {event.passedCount}✓
            </Text>
            <Text color={colors.text.dim}>/</Text>
            <Text color={colors.text.muted} bold>
              {event.totalCount}
            </Text>
          </Box>
        </Box>

        {/* Phase stepper */}
        <Box flexDirection="row" alignItems="center" marginTop={0}>
          {event.phases.map((phase, index) => {
            const st = phaseState(phase, event.stepIndex, allDone, colors);
            return (
              <Box key={phase} flexDirection="row" alignItems="center">
                <Text color={st.color} bold>
                  {st.icon}
                </Text>
                <Text color={st.color}>{LIFECYCLE_LABEL[phase]}</Text>
                {index < event.phases.length - 1 ? <Text color={colors.text.dim}> → </Text> : null}
              </Box>
            );
          })}
        </Box>

        {/* Cumulative pass bar */}
        <Box flexDirection="row" alignItems="center" marginTop={0} marginBottom={1}>
          <Text color={colors.text.dim}>assertions </Text>
          <Text color={colors.status.success}>{'\u2588'.repeat(filled)}</Text>
          <Text color={colors.text.muted}>{'\u2591'.repeat(BAR_WIDTH - filled)}</Text>
          <Text color={colors.text.bright} bold>
            {' '}
            {percent}%
          </Text>
        </Box>

        {/* Assertions */}
        {event.assertions.length > 0 ? (
          <Box flexDirection="column" paddingLeft={1}>
            {event.assertions.map((a, idx) => (
              <Box key={idx} flexDirection="row" alignItems="center">
                <Text color={assertionColor(a.passed, colors)}>{a.passed ? '✔ ' : '✘ '}</Text>
                <Text color={a.passed ? colors.text.bright : colors.status.error} wrap="truncate-end">
                  {a.label}
                </Text>
                {a.detail ? <Text color={colors.text.dim}> — {a.detail}</Text> : null}
              </Box>
            ))}
          </Box>
        ) : null}

        {/* Rejected edge-case ops */}
        {event.rejectedOps && event.rejectedOps.length > 0 ? (
          <Box flexDirection="column" paddingLeft={1} marginTop={0}>
            <Box flexDirection="row">
              <Text color={colors.status.warning} bold>
                ⊘ REJECTED EDGE CASES
              </Text>
              <Text color={colors.text.dim}> ({event.rejectedOps.length})</Text>
            </Box>
            {event.rejectedOps.map((r, idx) => (
              <Box key={idx} flexDirection="row" paddingLeft={1}>
                <Text color={colors.status.warning}>⊘ </Text>
                <Text color={colors.text.muted} wrap="truncate-end">
                  {r.op}
                </Text>
                <Text color={colors.text.dim}> — {r.reason}</Text>
              </Box>
            ))}
          </Box>
        ) : null}

        {/* Summary footer */}
        <Box flexDirection="row" paddingLeft={1} marginTop={0}>
          <Text color={colors.text.muted} italic wrap="truncate-end">
            {allDone
              ? `Lifecycle complete — ${event.passedCount}/${event.totalCount} assertions passed. Board persisted + verified after reload.`
              : `Waiting for phases to land… latest: ${LIFECYCLE_LABEL[event.phase]} · ${event.scenario}`}
          </Text>
        </Box>
      </Box>
    </Box>
  );
});

TodoLifecycleReportBlock.displayName = 'TodoLifecycleReportBlock';
