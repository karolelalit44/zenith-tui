import { Box, Text } from 'ink';
import React from 'react';
import { getToolStepPrimaryParam, getToolVerbLabel, SHELL_TOOL_SET } from '../../../constants/toolDisplay';
import { useTheme } from '../../../theme/ThemeContext';
import type { ToolCallEvent, ToolResultEvent } from '../../../types/scenario';
import { truncateEnd } from '../../../utils/text';

interface ToolTraceBlockProps {
  event: ToolCallEvent | ToolResultEvent;
}

function renderValue(val: unknown): string {
  if (val === null || val === undefined) return '';
  if (typeof val === 'string') return truncateEnd(val, 60);
  if (typeof val === 'number' || typeof val === 'boolean') return String(val);
  return truncateEnd(JSON.stringify(val), 60);
}

export const ToolTraceBlock: React.FC<ToolTraceBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  if (event.kind === 'tool_call') {
    const primary = getToolStepPrimaryParam(event.tool, event.params);
    return (
      <Box flexDirection="row" alignItems="center" width="100%" marginBottom={1} paddingX={1}>
        <Text color={theme.colors.text.dim}>→ </Text>
        <Text color={theme.colors.text.bright} bold>
          {getToolVerbLabel(event.tool)}
        </Text>
        {primary && (
          <>
            <Text color={theme.colors.text.dim}> </Text>
            <Text color={theme.colors.text.muted}>
              {primary.key}: {primary.value}
            </Text>
          </>
        )}
      </Box>
    );
  }

  const isShell = SHELL_TOOL_SET.has(event.tool.toLowerCase());
  const statusColor = isShell
    ? theme.colors.text.bright
    : event.success
      ? theme.colors.status.success
      : theme.colors.status.error;
  const statusGlyph = isShell ? '→' : event.success ? '' : '✗';
  const detail = event.error || (event.output ? renderValue(event.output) : '');
  return (
    <Box flexDirection="row" alignItems="center" width="100%" marginBottom={1} paddingX={1}>
      <Text color={statusColor} bold>
        {statusGlyph} {getToolVerbLabel(event.tool)}
      </Text>
      {detail && (
        <>
          <Text color={theme.colors.text.dim}> </Text>
          <Text color={theme.colors.text.muted} wrap="wrap">
            {detail}
          </Text>
        </>
      )}
    </Box>
  );
});
