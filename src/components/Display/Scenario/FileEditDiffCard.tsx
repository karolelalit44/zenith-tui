import { Box, Text } from 'ink';
import React from 'react';
import { ASCII_SPINNER_FRAMES } from '../../../constants/animation';
import { useTickAnimation } from '../../../hooks/useTickAnimation';
import { useTheme } from '../../../theme/ThemeContext';
import type { FileEditEvent } from '../../../types/scenario';
import { highlightCode } from '../../../utils/syntaxHighlight';
import type { EventRenderContext } from './componentRegistry';

interface FileEditDiffCardProps {
  event: FileEditEvent;
  context?: EventRenderContext;
}

const MAX_VISIBLE_LINES = 25;

export const FileEditDiffCard: React.FC<FileEditDiffCardProps> = React.memo(({ event, context }) => {
  const { theme } = useTheme();
  const spinnerTick = useTickAnimation(100);
  const isLive = context?.isRunning && !context?.isHistorical;
  const totalLines = event.removedLines.length + event.addedLines.length;
  const ext = event.filePath.split('.').pop() || event.language;

  const visibleRemoved = event.removedLines.slice(0, MAX_VISIBLE_LINES);
  const remainingBudget = MAX_VISIBLE_LINES - visibleRemoved.length;
  const visibleAdded = event.addedLines.slice(0, remainingBudget);
  const hiddenCount = totalLines - (visibleRemoved.length + visibleAdded.length);

  const displayPath = event.filePath.includes('/')
    ? event.filePath.split('/').slice(-2).join('/')
    : event.filePath;

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
        <Text color={isLive ? theme.colors.status.info : theme.colors.status.warning} bold>
          {isLive ? `[EDITING FILE] ${ASCII_SPINNER_FRAMES[spinnerTick % 4]}` : '[MODIFY]'}
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.text.bright} bold>
          {displayPath}
        </Text>
        <Text color={theme.colors.text.muted}>
          {' '}
          (-{event.removedLines.length} +{event.addedLines.length})
        </Text>
      </Box>

      <Box flexDirection="column" width="100%" borderStyle="single" borderColor={theme.colors.border.muted} paddingX={1}>
        {visibleRemoved.map((line, idx) => (
          <Box key={`rm-${idx}`} flexDirection="row" width="100%">
            <Box width={4} flexShrink={0}>
              <Text color={theme.colors.code.lineNum}>{idx + 1}</Text>
            </Box>
            <Box width={2} flexShrink={0}>
              <Text color={theme.colors.diff.removeFg}>-</Text>
            </Box>
            <Box flexShrink={1}>
              <Text color={theme.colors.diff.removeFg} strikethrough wrap="wrap">
                {line.text}
              </Text>
            </Box>
          </Box>
        ))}

        {visibleAdded.map((line, idx) => (
          <Box key={`add-${idx}`} flexDirection="row" width="100%">
            <Box width={4} flexShrink={0}>
              <Text color={theme.colors.code.lineNum}>{visibleRemoved.length + idx + 1}</Text>
            </Box>
            <Box width={2} flexShrink={0}>
              <Text color={theme.colors.diff.addFg}>+</Text>
            </Box>
            <Box flexShrink={1}>
              <Text wrap="wrap">{highlightCode(line.text, ext)}</Text>
            </Box>
          </Box>
        ))}

        {hiddenCount > 0 && (
          <Box flexDirection="row" marginTop={1}>
            <Text color={theme.colors.text.muted}> ... {hiddenCount} more lines</Text>
          </Box>
        )}
      </Box>
    </Box>
  );
});
