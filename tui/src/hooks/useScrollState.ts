import { useCallback, useEffect, useRef, useState } from 'react';

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
  const [scrollState, setScrollState] = useState<ScrollState>({
    isUserScrolled: false,
    scrollOffset: 0,
    viewportHeight: initialViewportHeight,
    contentHeight: 0,
  });

  const lastAutoScrollRef = useRef<number>(0);
  const AUTOSCROLL_GRACE_PERIOD = 1500;

  useEffect(() => {
    const updateViewport = () => {
      const height = process.stdout.rows ? process.stdout.rows - 4 : initialViewportHeight;
      setScrollState((prev) => ({ ...prev, viewportHeight: height }));
    };

    updateViewport();
    process.stdout.on('resize', updateViewport);
    return () => {
      process.stdout.off('resize', updateViewport);
    };
  }, [initialViewportHeight]);

  const scrollUp = useCallback((lines?: number) => {
    const scrollAmount = lines ?? 5;
    setScrollState((prev) => {
      const newOffset = Math.max(0, prev.scrollOffset - scrollAmount);
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
      const newOffset = Math.min(maxOffset, prev.scrollOffset + scrollAmount);
      const atBottom = newOffset >= maxOffset - 2;

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
      const now = Date.now();
      const wasAutoScrollRecent = now - lastAutoScrollRef.current < AUTOSCROLL_GRACE_PERIOD;

      if (!prev.isUserScrolled || wasAutoScrollRecent) {
        const maxOffset = Math.max(0, height - prev.viewportHeight);
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
