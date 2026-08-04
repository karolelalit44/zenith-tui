import { Text } from 'ink';
import React, { useEffect, useState } from 'react';
import { ASCII_SPINNER_FRAMES } from '../../constants/animation';

interface RunningSpinnerProps {
  color?: string;
}

/** Isolated tick so idle composer frames never re-render just to spin. */
export const RunningSpinner: React.FC<RunningSpinnerProps> = React.memo(({ color }) => {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setTick((t) => (t + 1) % ASCII_SPINNER_FRAMES.length), 150);
    return () => clearInterval(timer);
  }, []);

  return <Text color={color}>{ASCII_SPINNER_FRAMES[tick]}</Text>;
});

RunningSpinner.displayName = 'RunningSpinner';
