import { Box, Text } from 'ink';
import React from 'react';
import { useTerminalDimensions } from '../../../hooks/useTerminalDimensions';
import { useTheme } from '../../../theme/ThemeContext';
import type { FileAttachment } from '../../../types/scenario';

interface UserMessageBlockProps {
  prompt: string;
  model?: string;
  /**
   * Short timestamp frozen at turn creation: "HH:MM" (e.g. "12:08").
   * Used when terminal width < 80 columns.
   */
  timestamp?: string;
  /**
   * Long timestamp frozen at turn creation: "HH:MM, DD Mon" (e.g. "12:08, 12 Aug").
   * Used when terminal width >= 80 columns.
   */
  timestampLong?: string;
  /** Files/folders attached to this turn (rendered as chips). */
  attachments?: FileAttachment[];
}

/**
 * Renders a user message block with:
 *   - Full terminal-width background highlight bar for the user prompt
 *   - Clean metadata row: model label on far left, timestamp on far right
 *
 * Spacing and sizing:
 *   Uses explicit numeric width (terminal columns - 2) so Ink's <Static>
 *   renderer stretches the background color bar and metadata across the
 *   full screen width cleanly without collapse.
 */
export const UserMessageBlock: React.FC<UserMessageBlockProps> = React.memo(
  ({ prompt, model, timestamp, timestampLong }) => {
    const { theme } = useTheme();
    const { columns } = useTerminalDimensions();

    const termCols = columns || process.stdout.columns || 80;
    // App container has paddingX={1}, so inner usable width is (termCols - 2).
    const contentWidth = Math.max(30, termCols - 2);

    // Pick frozen timestamp display string
    const displayTime = termCols >= 80 ? (timestampLong ?? timestamp ?? '') : (timestamp ?? '');

    // Resolve model label
    const modelLabel = model ?? '';

    return (
      <Box flexDirection="column" width={contentWidth} marginTop={1} marginBottom={1}>
        {/* ── Full-width prompt bar with theme background fill ── */}
        <Box
          flexDirection="row"
          width={contentWidth}
          backgroundColor={theme.colors.code.background}
          paddingX={2}
          paddingY={1}
        >
          <Box marginRight={1} flexShrink={0}>
            <Text color={theme.colors.text.emerald} bold>
              ❯
            </Text>
          </Box>
          <Box flexGrow={1} flexShrink={1}>
            <Text color={theme.colors.text.bright} wrap="wrap" bold>
              {prompt}
            </Text>
          </Box>
        </Box>

        {/* ── Metadata row: model on far left, timestamp on far right ── */}
        <Box flexDirection="row" justifyContent="space-between" width={contentWidth} paddingLeft={2} paddingRight={2}>
          {modelLabel ? (
            <Text color={theme.colors.text.muted} wrap="truncate-end">
              ◇ <Text color={theme.colors.text.dim}>{modelLabel}</Text>
            </Text>
          ) : (
            <Text />
          )}

          {displayTime ? (
            <Text color={theme.colors.text.dim} wrap="truncate-end">
              {displayTime}
            </Text>
          ) : null}
        </Box>
      </Box>
    );
  },
);

UserMessageBlock.displayName = 'UserMessageBlock';
