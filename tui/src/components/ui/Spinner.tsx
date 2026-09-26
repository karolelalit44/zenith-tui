import { Text } from 'ink';
import React from 'react';
import { SPINNER_FRAMES } from '../../constants/animation';
import { useAnimationTick } from '../../context/AnimationContext';

interface SpinnerProps {
  color?: string;
  bold?: boolean;
  suffix?: string;
}

/**
 * Isolated 100ms-tick leaf. The only component that consumes the shared
 * animation tick here — memoized parents with stable props never re-render
 * per tick; only this tiny node does.
 *
 * Unstyled usage returns a bare fragment so the frame glyph inherits the
 * surrounding <Text> styling (color/bold). Pass `color`/`bold` only when the
 * spinner must carry its own style. `suffix` opts into a trailing space.
 */
export const Spinner: React.FC<SpinnerProps> = React.memo(({ color, bold = false, suffix = '' }) => {
  const tick = useAnimationTick();
  const frame = SPINNER_FRAMES[tick % SPINNER_FRAMES.length];
  if (color || bold) {
    return (
      <Text color={color} bold={bold}>
        {frame}
        {suffix}
      </Text>
    );
  }
  return (
    <>
      {frame}
      {suffix}
    </>
  );
});

Spinner.displayName = 'Spinner';
