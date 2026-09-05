import { Box, Text, useInput } from 'ink';
import React from 'react';
import { ModalFooter } from '../../components/ui/ModalFooter';
import { RoundedBox } from '../../components/ui/RoundedBox';
import type { ContextInfoSnapshot } from '../../hooks/useConversation';
import { useProvider } from '../../hooks/useProvider';
import { estimateTokensForEvents, formatTokenCount } from '../../services/api/tokenEstimationService';
import { WORKSPACE_FILES } from '../../services/fileExplorer';
import { useTheme } from '../../theme/ThemeContext';
import type { ScenarioEvent } from '../../types/scenario';

interface ContextModalProps {
  totalTokens: number;
  runningEvents?: ScenarioEvent[];
  onClose: () => void;
  /** Cumulative run/API token usage (telemetry). */
  runTokens?: number;
  runPrompt?: number;
  runCompletion?: number;
  runEstimated?: boolean;
  /** Latest composed-context occupancy snapshot; preferred over estimates. */
  contextInfo?: ContextInfoSnapshot | null;
}

export const ContextModal: React.FC<ContextModalProps> = ({
  totalTokens,
  runningEvents = [],
  onClose,
  runTokens = 0,
  runPrompt,
  runCompletion,
  runEstimated: _runEstimated = false,
  contextInfo,
}) => {
  const { theme } = useTheme();
  const { activeProvider } = useProvider();

  const activeModelId = activeProvider.config.model || activeProvider.meta.defaultModel;
  const activeModelInfo = activeProvider.meta.availableModels?.find((m) => m.id === activeModelId);
  const maxTokens = activeModelInfo?.context_window || 200000;

  // Composed-context occupancy only. Prefer the backend success snapshot; fall
  // back to the live estimate solely for legacy runs that never reported it.
  const composedSnapshot = contextInfo && contextInfo.total > 0 ? contextInfo : null;
  const contextUsed = composedSnapshot ? composedSnapshot.used : totalTokens + estimateTokensForEvents(runningEvents);
  const contextTotal = composedSnapshot ? composedSnapshot.total : maxTokens;
  // Raw occupancy ratio is kept before clamping so overflow (>100%) is
  // surfaced explicitly instead of silently flattened to a full bar.
  const rawPercent = Math.round((contextUsed / Math.max(1, contextTotal)) * 100);
  const overflow = rawPercent > 100;
  const contextPercent = Math.min(100, Math.max(0, rawPercent));

  useInput((_char, key) => {
    if (key.escape || key.return) {
      onClose();
    }
  });

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
            {formatTokenCount(contextUsed)} / {formatTokenCount(contextTotal)} ({contextPercent}%)
          </Text>
        </Box>

        {overflow && (
          <Box flexDirection="row" alignItems="center" marginBottom={1}>
            <Text color={theme.colors.status.error} bold>
              ⚠ OVERFLOW
            </Text>
            <Text color={theme.colors.text.muted}> composed context exceeds the window (raw {rawPercent}%)</Text>
          </Box>
        )}

        <Box flexDirection="row" alignItems="center" marginBottom={1}>
          <Text color={theme.colors.status.success}>[{bar}]</Text>
        </Box>

        {runTokens > 0 ? (
          <Box flexDirection="row" alignItems="center" marginBottom={1}>
            <Text color={theme.colors.text.muted} bold>
              RUN USAGE{' '}
            </Text>
            <Text color={theme.colors.text.bright}>
              {formatTokenCount(runTokens)}
              {typeof runPrompt === 'number' && runPrompt > 0 ? ` · prompt ${formatTokenCount(runPrompt)}` : ''}
              {typeof runCompletion === 'number' && runCompletion > 0
                ? ` · completion ${formatTokenCount(runCompletion)}`
                : ''}
            </Text>
          </Box>
        ) : null}

        <Box
          flexDirection="row"
          marginBottom={1}
          borderStyle="single"
          borderTop={true}
          borderBottom={true}
          borderLeft={false}
          borderRight={false}
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

        {sampleFiles.length === 0 ? (
          <Box paddingY={1}>
            <Text color={theme.colors.text.dim} italic>
              No workspace files loaded.
            </Text>
          </Box>
        ) : (
          sampleFiles.map((f, idx) => {
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
          })
        )}

        <Box
          marginTop={1}
          paddingTop={1}
          borderStyle="single"
          borderTop={true}
          borderBottom={false}
          borderLeft={false}
          borderRight={false}
          borderColor={theme.colors.border.muted}
        >
          <Text color={theme.colors.text.muted}>
            <ModalFooter shortcuts={[{ key: '[Esc]', label: 'to exit Context Window' }]} />
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
