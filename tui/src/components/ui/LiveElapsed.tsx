import { Text } from 'ink';
import React from 'react';
import { useAnimationTick } from '../../context/AnimationContext';
import { formatDuration } from '../../utils/text';

interface LiveElapsedProps {
  /** Epoch ms the row's own partial step began. */
  startedAt: number;
  color?: string;
  prefix?: string;
}

/**
 * Isolated 100ms-tick leaf that renders a running "~ N s" duration measured
 * from `startedAt`. The shared tick only drives this tiny node, so the parent
 * card stays memoized while the pill ticks up.
 */
export const LiveElapsed: React.FC<LiveElapsedProps> = React.memo(({ startedAt, color, prefix = '~ ' }) => {
  useAnimationTick();
  const elapsedMs = Math.max(0, Date.now() - startedAt);
  return (
    <Text color={color}>
      {prefix}
      {formatDuration(elapsedMs)}
    </Text>
  );
});

LiveElapsed.displayName = 'LiveElapsed';
