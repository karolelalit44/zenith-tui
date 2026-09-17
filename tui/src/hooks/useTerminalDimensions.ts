import { useEffect, useRef, useState } from 'react';

export interface TerminalDimensions {
  columns: number;
  rows: number;
}

type ResizeListener = (dims: TerminalDimensions) => void;

function readTerminalDimensions(): TerminalDimensions {
  return {
    columns: process.stdout.columns ?? 80,
    rows: process.stdout.rows ?? 24,
  };
}

let currentDimensions = readTerminalDimensions();
const resizeListeners = new Set<ResizeListener>();
let resizeListenerAttached = false;

function handleResize(): void {
  currentDimensions = readTerminalDimensions();
  for (const listener of resizeListeners) {
    listener(currentDimensions);
  }
}

function ensureResizeListener(): void {
  if (resizeListenerAttached) {
    return;
  }

  currentDimensions = readTerminalDimensions();
  process.stdout.on('resize', handleResize);
  resizeListenerAttached = true;
}

function releaseResizeListener(): void {
  if (!resizeListenerAttached || resizeListeners.size > 0) {
    return;
  }

  process.stdout.off('resize', handleResize);
  resizeListenerAttached = false;
}

export function subscribeTerminalResize(listener: ResizeListener): () => void {
  resizeListeners.add(listener);
  ensureResizeListener();

  return () => {
    resizeListeners.delete(listener);
    releaseResizeListener();
  };
}

export function useTerminalDimensions(onResizeComplete?: (dims: TerminalDimensions) => void): TerminalDimensions {
  const [dimensions, setDimensions] = useState<TerminalDimensions>(() => readTerminalDimensions());

  const onResizeRef = useRef(onResizeComplete);
  useEffect(() => {
    onResizeRef.current = onResizeComplete;
  }, [onResizeComplete]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;

    const unsubscribe = subscribeTerminalResize((dims) => {
      setDimensions(dims);

      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        timer = null;
        if (onResizeRef.current) {
          onResizeRef.current(dims);
        }
      }, 120);
    });

    return () => {
      if (timer) clearTimeout(timer);
      unsubscribe();
    };
  }, []);

  return dimensions;
}
