import { useEffect, useState } from 'react';

export function useTickAnimation(interval: number, enabled = true): number {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => setTick((t) => t + 1), interval);
    return () => clearInterval(id);
  }, [interval, enabled]);

  return tick;
}
