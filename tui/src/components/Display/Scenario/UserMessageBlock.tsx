import { Box, Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { modelStore } from '../../../services/providers/ModelStore';
import { useTheme } from '../../../theme/ThemeContext';

interface UserMessageBlockProps {
  prompt: string;
  model?: string;
}

export const UserMessageBlock: React.FC<UserMessageBlockProps> = React.memo(({ prompt, model }) => {
  const { theme } = useTheme();
  const [columns, setColumns] = useState(() => process.stdout.columns ?? 80);

  useEffect(() => {
    const handleResize = () => {
      setColumns(process.stdout.columns ?? 80);
    };
    process.stdout.on('resize', handleResize);
    return () => {
      process.stdout.off('resize', handleResize);
    };
  }, []);

  const isCompact = columns < 75;

  const now = new Date();
  const timeStr = isCompact
    ? now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
    : `${now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })}, ${now.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`;

  const boxWidth = Math.max(0, columns - 2);
  const modelLabel = model || (modelStore.current ? modelStore.toDisplayString(modelStore.current) : '');

  return (
    <Box flexDirection="column" width={boxWidth} marginBottom={1} paddingX={1}>
      <Box
        flexDirection="row"
        width="100%"
        backgroundColor={theme.colors.bg.modal}
        borderStyle="round"
        borderColor={theme.colors.bg.modal}
        paddingX={1}
        paddingY={0}
      >
        <Text color={theme.colors.text.bright} wrap="wrap">
          {prompt}
        </Text>
      </Box>
      <Box flexDirection="row" justifyContent="space-between" width="100%" marginTop={0} paddingX={1}>
        {modelLabel ? (
          <Text color={theme.colors.text.muted}>
            ◇ <Text color={theme.colors.text.dim}>{modelLabel}</Text>
          </Text>
        ) : (
          <Box />
        )}
        <Text color={theme.colors.text.dim}>{timeStr}</Text>
      </Box>
    </Box>
  );
});
