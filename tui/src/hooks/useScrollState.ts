import { useCallback, useEffect, useRef, useState } from 'react';
import { useTerminalDimensions } from './useTerminalDimensions';

export interface ScrollState {
  isUserScrolled: boolean;
  scrollOffset: number;
  viewportHeight: number;
  contentHeight: number;
}

export interface UseScrollStateReturn {
  scrollState: ScrollState;
  scrollUp: (lines?: number) => void;
  scrollDown: (lines?: number) => void;
  scrollToTop: () => void;
  scrollToBottom: () => void;
  resetScroll: () => void;
  updateContentHeight: (height: number) => void;
}

export function useScrollState(initialViewportHeight = 20): UseScrollStateReturn {
  const { rows } = useTerminalDimensions();
  const [scrollState, setScrollState] = useState<ScrollState>({
    isUserScrolled: false,
    scrollOffset: 0,
    viewportHeight: initialViewportHeight,
    contentHeight: 0,
  });

  const lastAutoScrollRef = useRef<number>(0);

  useEffect(() => {
    const height = rows ? Math.max(5, rows - 9) : initialViewportHeight;
    setScrollState((prev) => ({ ...prev, viewportHeight: height }));
  }, [rows, initialViewportHeight]);

  const scrollUp = useCallback((lines?: number) => {
    const scrollAmount = lines ?? 5;
    setScrollState((prev) => {
      const currentOffset = prev.isUserScrolled
        ? prev.scrollOffset
        : Math.max(0, prev.contentHeight - prev.viewportHeight);
      const newOffset = Math.max(0, currentOffset - scrollAmount);
      return {
        ...prev,
        scrollOffset: newOffset,
        isUserScrolled: true,
      };
    });
  }, []);

  const scrollDown = useCallback((lines?: number) => {
    const scrollAmount = lines ?? 5;
    setScrollState((prev) => {
      const maxOffset = Math.max(0, prev.contentHeight - prev.viewportHeight);
      const currentOffset = prev.isUserScrolled ? prev.scrollOffset : maxOffset;
      const newOffset = Math.min(maxOffset, currentOffset + scrollAmount);
      const atBottom = newOffset >= maxOffset;

      return {
        ...prev,
        scrollOffset: newOffset,
        isUserScrolled: !atBottom,
      };
    });
  }, []);

  const scrollToTop = useCallback(() => {
    setScrollState((prev) => ({
      ...prev,
      scrollOffset: 0,
      isUserScrolled: true,
    }));
  }, []);

  const scrollToBottom = useCallback(() => {
    setScrollState((prev) => {
      const maxOffset = Math.max(0, prev.contentHeight - prev.viewportHeight);
      lastAutoScrollRef.current = Date.now();
      return {
        ...prev,
        scrollOffset: maxOffset,
        isUserScrolled: false,
      };
    });
  }, []);

  const resetScroll = useCallback(() => {
    lastAutoScrollRef.current = Date.now();
    setScrollState((prev) => ({
      ...prev,
      scrollOffset: 0,
      isUserScrolled: false,
    }));
  }, []);

  const updateContentHeight = useCallback((height: number) => {
    setScrollState((prev) => {
      if (prev.contentHeight === height) return prev;
      const maxOffset = Math.max(0, height - prev.viewportHeight);

      if (!prev.isUserScrolled) {
        return {
          ...prev,
          contentHeight: height,
          scrollOffset: maxOffset,
        };
      }

      return { ...prev, contentHeight: height };
    });
  }, []);

  return {
    scrollState,
    scrollUp,
    scrollDown,
    scrollToTop,
    scrollToBottom,
    resetScroll,
    updateContentHeight,
  };
}
