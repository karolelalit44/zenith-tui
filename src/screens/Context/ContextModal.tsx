import { Box, Text, useInput } from 'ink';
import React from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { WORKSPACE_FILES } from '../../services/fileExplorerService';
import { useTheme } from '../../theme/ThemeContext';

interface ContextModalProps {
  totalTokens: number;
  maxTokens?: number;
  onClose: () => void;
}

export const ContextModal: React.FC<ContextModalProps> = ({ totalTokens, maxTokens = 200000, onClose }) => {
  const { theme } = useTheme();

  useInput((_char, key) => {
    if (key.escape || key.return) {
      onClose();
    }
  });

  const contextPercent = Math.min(100, Math.round((totalTokens / maxTokens) * 100));
  const totalBlocks = 20;
  const filledBlocks = Math.max(0, Math.min(totalBlocks, Math.round((contextPercent / 100) * totalBlocks)));
  const bar = '█'.repeat(filledBlocks) + '░'.repeat(totalBlocks - filledBlocks);

  const sampleFiles = WORKSPACE_FILES.filter((f) => !f.isDir).slice(0, 7);

  return (
    <RoundedBox title="CONTEXT WINDOW INSPECTOR" borderColor={theme.colors.border.active} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        <Box flexDirection="row" alignItems="center" marginBottom={1}>
          <Text color={theme.colors.text.emerald} bold>
            [CONTEXT USAGE]{' '}
          </Text>
          <Text color={theme.colors.text.bright} bold>
            {totalTokens.toLocaleString()} / {maxTokens.toLocaleString()} Tokens ({contextPercent}%)
          </Text>
        </Box>

        <Box flexDirection="row" alignItems="center" marginBottom={1}>
          <Text color={theme.colors.status.success}>[{bar}]</Text>
        </Box>

        <Box
          flexDirection="row"
          marginBottom={1}
          borderStyle="single"
          borderTop={true}
          borderBottom={true}
          borderColor={theme.colors.border.muted}
        >
          <Box width={32}>
            <Text color={theme.colors.text.muted} bold>
              ACTIVE FILE / RESOURCE
            </Text>
          </Box>
          <Box width={16}>
            <Text color={theme.colors.text.muted} bold>
              SIZE
            </Text>
          </Box>
          <Box width={16}>
            <Text color={theme.colors.text.muted} bold>
              EST. TOKENS
            </Text>
          </Box>
        </Box>

        {sampleFiles.map((f, idx) => (
          <Box key={idx} flexDirection="row" alignItems="center" width="100%">
            <Box width={32}>
              <Text color={theme.colors.text.dim} wrap="truncate-end">
                {f.relativePath}
              </Text>
            </Box>
            <Box width={16}>
              <Text color={theme.colors.text.dim}>{f.sizeFormatted || '1.2 KB'}</Text>
            </Box>
            <Box width={16}>
              <Text color={theme.colors.text.dim}>{Math.round(150 + idx * 85)} tokens</Text>
            </Box>
          </Box>
        ))}

        <Box marginTop={1} paddingTop={1} borderStyle="single" borderTop={true} borderColor={theme.colors.border.muted}>
          <Text color={theme.colors.text.muted}>
            Press <Text color={theme.colors.text.emerald}>[Esc]</Text> to exit Context Window
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
