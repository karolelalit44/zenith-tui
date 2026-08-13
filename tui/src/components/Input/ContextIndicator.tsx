import { Box, Text } from 'ink';
import React from 'react';
import { type ContextLevel, contextLabel, contextLevelForPercent } from '../../config/context';
import { SPINNER_FRAMES } from '../../constants/animation';
import { useAnimationTick } from '../../context/AnimationContext';
import { formatTokenCount } from '../../services/api/tokenEstimationService';
import { useTheme } from '../../theme/ThemeContext';
import type { ContextCompactionFlowEvent } from '../../types/scenario';

interface ContextIndicatorProps {
  percent: number;
  totalTokens: number;
  compaction?: ContextCompactionFlowEvent | null;
}

export const ContextIndicator: React.FC<ContextIndicatorProps> = React.memo(({ percent, totalTokens, compaction }) => {
  const { theme } = useTheme();
  const tick = useAnimationTick();
  const level: ContextLevel = contextLevelForPercent(percent);
  const label = contextLabel(level);

  let color = theme.colors.text.dim;
  let text: string;
  if (level === 'required') {
    color = theme.colors.status.warning;
  } else if (level === 'preparing') {
    color = theme.colors.status.info;
  }

  if (compaction && compaction.phase !== 'ready' && compaction.phase !== 'failed') {
    text = 'Compacting…';
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
    </Box>
  );
});

ContextIndicator.displayName = 'ContextIndicator';
