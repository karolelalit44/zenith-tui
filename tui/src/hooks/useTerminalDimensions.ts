import { useEffect, useRef, useState } from 'react';

export interface TerminalDimensions {
  columns: number;
  rows: number;
}

export function useTerminalDimensions(onResizeComplete?: (dims: TerminalDimensions) => void): TerminalDimensions {
  const [dimensions, setDimensions] = useState<TerminalDimensions>(() => ({
    columns: process.stdout.columns ?? 80,
    rows: process.stdout.rows ?? 24,
  }));

  const onResizeRef = useRef(onResizeComplete);
  useEffect(() => {
    onResizeRef.current = onResizeComplete;
  }, [onResizeComplete]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;

    const handleResize = () => {
      const cols = process.stdout.columns ?? 80;
      const rws = process.stdout.rows ?? 24;

      setDimensions({ columns: cols, rows: rws });

      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        timer = null;
        if (onResizeRef.current) {
          onResizeRef.current({ columns: cols, rows: rws });
        }
      }, 120);
    };

    process.stdout.on('resize', handleResize);
    return () => {
      if (timer) clearTimeout(timer);
      process.stdout.off('resize', handleResize);
    };
  }, []);

  return dimensions;
}
