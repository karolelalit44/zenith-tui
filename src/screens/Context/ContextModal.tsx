import { Box, Text, useInput } from 'ink';
import React, { useMemo } from 'react';
import { ModalFooter } from '../../components/ui/ModalFooter';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { estimateTokensForEvents, formatTokenCount } from '../../services/data/tokenEstimationService';
import { WORKSPACE_FILES } from '../../services/fileExplorerService';
import { useTheme } from '../../theme/ThemeContext';
import type { ScenarioEvent } from '../../types/scenario';

interface ContextModalProps {
  totalTokens: number;
  runningEvents?: ScenarioEvent[];
  maxTokens?: number;
  onClose: () => void;
}

export const ContextModal: React.FC<ContextModalProps> = ({
  totalTokens,
  runningEvents = [],
  maxTokens = 200000,
  onClose,
}) => {
  const { theme } = useTheme();

  const liveTokens = useMemo(() => {
    return totalTokens + estimateTokensForEvents(runningEvents);
  }, [totalTokens, runningEvents]);

  useInput((_char, key) => {
    if (key.escape || key.return) {
      onClose();
    }
  });

  const contextPercent = Math.min(100, Math.round((liveTokens / maxTokens) * 100));
  const totalBlocks = 20;
  const filledBlocks = Math.max(0, Math.min(totalBlocks, Math.round((contextPercent / 100) * totalBlocks)));
  const bar = '█'.repeat(filledBlocks) + '░'.repeat(totalBlocks - filledBlocks);

  const sampleFiles = WORKSPACE_FILES.filter((f) => !f.isDir).slice(0, 7);

  const estimateFileTokens = (sizeFormatted: string | undefined): number => {
    const sizeStr = sizeFormatted || '1.2 KB';
    const match = sizeStr.match(/([\d.]+)\s*(KB|MB|GB)/i);
    if (!match) return 300;
    const value = Number.parseFloat(match[1]);
    const unit = match[2].toUpperCase();
    let bytes = value * 1024;
    if (unit === 'MB') bytes = value * 1024 * 1024;
    if (unit === 'GB') bytes = value * 1024 * 1024 * 1024;
    return Math.round(bytes / 4);
  };

  return (
    <RoundedBox title="CONTEXT WINDOW INSPECTOR" borderColor={theme.colors.border.active} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        <Box flexDirection="row" alignItems="center" marginBottom={1}>
          <Text color={theme.colors.text.emerald} bold>
            [CONTEXT USAGE]{' '}
          </Text>
          <Text color={theme.colors.text.bright} bold>
            {formatTokenCount(liveTokens)} ({contextPercent}%)
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

        {sampleFiles.map((f, idx) => {
          const fileTokens = estimateFileTokens(f.sizeFormatted);
          return (
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
                <Text color={theme.colors.text.dim}>{formatTokenCount(fileTokens)}</Text>
              </Box>
            </Box>
          );
        })}

        <Box marginTop={1} paddingTop={1} borderStyle="single" borderTop={true} borderColor={theme.colors.border.muted}>
          <Text color={theme.colors.text.muted}>
            <ModalFooter shortcuts={[{ key: '[Esc]', label: 'to exit Context Window' }]} />
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
