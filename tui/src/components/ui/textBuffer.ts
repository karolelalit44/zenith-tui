import type { Key } from 'ink';
import { useCallback, useState } from 'react';

export interface TextBuffer {
  value: string;
  cursor: number;
  handleKey: (char: string, key: Key) => void;
  reset: (next?: string) => void;
}

export function useTextBuffer(initial = ''): TextBuffer {
  const [value, setValue] = useState(initial);
  const [cursor, setCursor] = useState(initial.length);

  const reset = useCallback((next = '') => {
    setValue(next);
    setCursor(next.length);
  }, []);

  const handleKey = useCallback(
    (char: string, key: Key) => {
      if (key.leftArrow) {
        setCursor((c) => Math.max(0, c - 1));
        return;
      }
      if (key.rightArrow) {
        setCursor((c) => Math.min(value.length, c + 1));
        return;
      }
      if (key.home) {
        setCursor(0);
        return;
      }
      if (key.end) {
        setCursor(value.length);
        return;
      }
      if (key.delete) {
        if (cursor >= value.length) return;
        const chars = [...value];
        chars.splice(cursor, 1);
        setValue(chars.join(''));
        return;
      }
      if (key.backspace) {
        if (cursor <= 0) return;
        const chars = [...value];
        chars.splice(cursor - 1, 1);
        setValue(chars.join(''));
        setCursor((c) => Math.max(0, c - 1));
        return;
      }
      if (!char) return;
      if (char.length === 1 && !char.match(/\s/u) && (char < ' ' || char === '\u007f')) return;
      const chars = [...value];
      chars.splice(cursor, 0, char);
      setValue(chars.join(''));
      setCursor(cursor + [...char].length);
    },
    [value, cursor],
  );

  return { value, cursor, handleKey, reset };
}

export function fuzzyScore(query: string, title: string, category = ''): number | null {
  const needle = query.trim().toLowerCase();
  if (!needle) return 0;
  const titleLower = title.toLowerCase();
  const catLower = category.toLowerCase();

  let titleScore: number | null = null;
  if (titleLower.includes(needle)) {
    titleScore = 100 - titleLower.indexOf(needle);
  } else {
    let ti = 0;
    let j = 0;
    let consec = 0;
    let bestConsec = 0;
    while (j < needle.length && ti < titleLower.length) {
      if (titleLower[ti] === needle[j]) {
        j++;
        consec++;
        bestConsec = Math.max(bestConsec, consec);
      } else {
        consec = 0;
      }
      ti++;
    }
    if (j === needle.length) {
      titleScore = 40 + bestConsec;
    }
  }

  const catMatch = catLower.includes(needle) ? 10 : 0;
  if (titleScore === null && catMatch === 0) return null;
  return (titleScore ?? 0) * 2 + catMatch;
}
