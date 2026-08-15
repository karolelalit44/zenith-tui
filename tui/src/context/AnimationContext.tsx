/**
 * AnimationContext — single shared 100ms tick for all animated components.
 *
 * Instead of every ToolStepCard, ProgressBar, MessageBlock, and LiveSpinner
 * each creating their own setInterval, they all subscribe to this one context.
 * This reduces render firings during live generation from N-timers to exactly 1.
 */
import React, { createContext, useContext, useEffect, useRef, useState } from 'react';

interface AnimationContextValue {
  tick: number;
}

const AnimationContext = createContext<AnimationContextValue>({ tick: 0 });

export const AnimationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [tick, setTick] = useState(0);
  const frameRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    frameRef.current = setInterval(() => setTick((t) => t + 1), 100);
    return () => {
      if (frameRef.current !== null) clearInterval(frameRef.current);
    };
  }, []);

  return <AnimationContext.Provider value={{ tick }}>{children}</AnimationContext.Provider>;
};

/**
 * Returns the current animation tick (increments every 100ms).
 * Use this instead of a local setInterval in components.
 */
export function useAnimationTick(): number {
  return useContext(AnimationContext).tick;
}
