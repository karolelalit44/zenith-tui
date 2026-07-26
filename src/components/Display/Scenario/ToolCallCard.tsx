import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { ASCII_SPINNER_FRAMES } from '../../../constants/animation';
import { useTheme } from '../../../theme/ThemeContext';
import type { ToolCallEvent } from '../../../types/scenario';
import type { EventRenderContext } from './componentRegistry';

interface ToolCallCardProps {
  event: ToolCallEvent;
  context?: EventRenderContext;
}

const SKIP_PARAMS = new Set([
  'content', 'file_content', 'old_content', 'new_content', 'data',
  'file_data', 'filetext', 'file_text', 'source', 'text',
  'body', 'input', 'output',
]);

function formatValue(val: unknown): string {
  if (val === null || val === undefined) return 'null';
  if (typeof val === 'string') {
    if (val.length > 80) return `${val.slice(0, 77)}...`;
    return val;
  }
  if (typeof val === 'number' || typeof val === 'boolean') return String(val);
  const str = JSON.stringify(val);
  if (str.length > 80) return `${str.slice(0, 77)}...`;
  return str;
}

export const ToolCallCard: React.FC<ToolCallCardProps> = React.memo(({ event, context }) => {
  const { theme } = useTheme();
  const isPending = context?.isRunning && !context?.isHistorical;
  const [frameIdx, setFrameIdx] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!isPending) return;
    const id = setInterval(() => {
      setFrameIdx((v) => (v + 1) % ASCII_SPINNER_FRAMES.length);
      setElapsed((v) => v + 1);
    }, 100);
    return () => clearInterval(id);
  }, [isPending]);

  const params = event.params || {};
  const entries = Object.entries(params)
    .filter(([key]) => !SKIP_PARAMS.has(key.toLowerCase()))
    .slice(0, 5);

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center">
        <Text color={theme.colors.status.info} bold>
          {isPending ? (
            <>[{ASCII_SPINNER_FRAMES[frameIdx % ASCII_SPINNER_FRAMES.length]} RUN] </>
          ) : (
            <>{'>'} RUN </>
          )}
        </Text>
        <Text color={theme.colors.text.bright} bold>
          {event.tool}
        </Text>
        {isPending && (
          <Text color={theme.colors.text.muted}> ({(elapsed / 10).toFixed(0)}s)</Text>
        )}
      </Box>

      {entries.length > 0 && (
        <Box flexDirection="column" paddingLeft={3}>
          {entries.map(([key, val]) => (
            <Box key={key} flexDirection="row">
              <Text color={theme.colors.text.muted}>{key}: </Text>
              <Text color={theme.colors.text.ethereal} wrap="wrap">
                {formatValue(val)}
              </Text>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
});
