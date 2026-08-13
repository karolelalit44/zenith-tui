import { Box, Text } from 'ink';
import React from 'react';
import { type ContextLevel, contextColor, contextLabel, contextLevelForPercent } from '../../config/context';
import { SPINNER_FRAMES } from '../../constants/animation';
import { useAnimationTick } from '../../context/AnimationContext';
import { formatTokenCount } from '../../services/api/tokenEstimationService';
import { useTheme } from '../../theme/ThemeContext';
import type { ContextCompactionFlowEvent } from '../../types/scenario';

interface ContextIndicatorProps {
  percent: number;
  totalTokens: number;
  compaction?: ContextCompactionFlowEvent | null;
  /** Optional handler to open the compaction details overlay (e.g. on activate). */
  onOpen?: () => void;
}

export const ContextIndicator: React.FC<ContextIndicatorProps> = React.memo(
  ({ percent, totalTokens, compaction, onOpen }) => {
    const { theme } = useTheme();
    const tick = useAnimationTick();
    const level: ContextLevel = contextLevelForPercent(percent);
    const label = contextLabel(level);

    const colorToken = contextColor(level);
    let color =
      colorToken === 'warning'
        ? theme.colors.status.warning
        : colorToken === 'info'
          ? theme.colors.status.info
          : theme.colors.text.dim;
    let text: string;

    if (compaction && compaction.phase !== 'ready' && compaction.phase !== 'failed') {
      if (typeof compaction.beforeTokens === 'number' && typeof compaction.afterTokens === 'number') {
        text = `Compacting… ${formatTokenCount(compaction.beforeTokens)} → ${formatTokenCount(compaction.afterTokens)}`;
      } else {
        text = 'Compacting…';
      }
      color = theme.colors.status.warning;
    } else if (compaction && compaction.phase === 'failed') {
      text = 'Compaction failed';
      color = theme.colors.status.warning;
    } else if (compaction && compaction.phase === 'ready') {
      text = `Context ${formatTokenCount(compaction.afterTokens ?? totalTokens)}`;
    } else if (label) {
      text = `Context ${percent}% · ${label}`;
    } else {
      text = `Context ${percent}%`;
    }

    const showSpinner = compaction && compaction.phase !== 'ready' && compaction.phase !== 'failed';

    return (
      <Box flexDirection="row" alignItems="center" flexShrink={0}>
        <Text color={color} bold>
          {showSpinner ? `${SPINNER_FRAMES[tick % SPINNER_FRAMES.length]} ` : null}
          {text}
        </Text>
        {onOpen ? <Text color={theme.colors.text.dim}> ⏎</Text> : null}
      </Box>
    );
  },
);

ContextIndicator.displayName = 'ContextIndicator';
