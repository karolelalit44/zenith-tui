import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { OutputCardProps, BuildStep } from './types';
import { KIND_META, STATUS_META } from './data/outputData';
import { WordDiffViewer } from '../WordDiffViewer';

const SEPARATOR = '─'.repeat(72);

const OutputHeader: React.FC<{ icon: string; title: string; status: keyof typeof STATUS_META; filePath?: string }> = ({
  icon, title, status, filePath,
}) => {
  const { theme } = useTheme();
  const kindColor = theme.colors.text.emerald;
  const statusMeta = STATUS_META[status];
  const statusColor = theme.colors.text[statusMeta.colorKey];

  return (
    <Box flexDirection="row" alignItems="center" marginBottom={1}>
      <Text color={kindColor}>{icon} </Text>
      <Text color={theme.colors.text.ethereal} bold>{title}</Text>
      {filePath && (
        <>
          <Text color={theme.colors.text.muted}> · </Text>
          <Text color={theme.colors.text.muted}>{filePath}</Text>
        </>
      )}
      <Box flexGrow={1} />
      <Text color={statusColor} bold>{statusMeta.label}</Text>
    </Box>
  );
};

const BuildSteps: React.FC<{ steps: BuildStep[] }> = ({ steps }) => {
  const { theme } = useTheme();
  return (
    <Box flexDirection="column" marginTop={1}>
      {steps.map((step, idx) => (
        <Box key={idx} flexDirection="row" alignItems="center">
          <Box width={2}>
            <Text color={step.success ? theme.colors.text.emerald : theme.colors.text.error}>
              {step.success ? '✔' : '✗'}
            </Text>
          </Box>
          <Box flexGrow={1}>
            <Text color={theme.colors.text.ethereal}>{step.label}</Text>
          </Box>
          <Text color={theme.colors.text.muted}>{step.duration}</Text>
        </Box>
      ))}
    </Box>
  );
};

export const OutputCard: React.FC<OutputCardProps> = ({ meta }) => {
  const { theme } = useTheme();

  return (
    <Box
      flexDirection="column"
      marginBottom={1}
      paddingX={1}
      borderStyle="round"
      borderColor={meta.status === 'error' ? theme.colors.text.error : theme.colors.border.muted}
    >
      <OutputHeader
        icon={meta.icon || KIND_META[meta.kind].icon}
        title={meta.title}
        status={meta.status}
        filePath={meta.filePath}
      />

      <Box>
        <Text color={theme.colors.border.muted}>{SEPARATOR}</Text>
      </Box>

      {meta.diff && (
        <Box marginTop={1}>
          <WordDiffViewer lines={meta.diff} />
        </Box>
      )}

      {meta.buildSteps && (
        <BuildSteps steps={meta.buildSteps} />
      )}

      {meta.message && (
        <Box marginTop={1} flexDirection="row">
          <Text color={theme.colors.text.muted}>  </Text>
          <Text color={theme.colors.text.ethereal}>{meta.message}</Text>
        </Box>
      )}

      {meta.elapsed && (
        <Box marginTop={1} flexDirection="row" justifyContent="flex-end">
          <Text color={theme.colors.text.muted}>completed in </Text>
          <Text color={theme.colors.text.emerald} bold>{meta.elapsed}</Text>
        </Box>
      )}
    </Box>
  );
};
