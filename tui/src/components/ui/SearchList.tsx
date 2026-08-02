import { Box, Text, useInput } from 'ink';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTheme } from '../../theme/ThemeContext';
import { fuzzyScore, useTextBuffer } from './textBuffer';

export interface SearchListAction<T> {
  label: string;
  onTrigger: (option: SearchListOption<T>) => void;
}

export interface SearchListOption<T = string> {
  title: string;
  value: T;
  description?: string;
  category?: string;
  disabled?: boolean;
  current?: boolean;
  gutter?: string;
  footer?: string;
  onSelect?: () => void;
}

interface SearchListProps<T> {
  title: string;
  options: SearchListOption<T>[];
  onSelect: (option: SearchListOption<T>) => void;
  onClose: () => void;
  placeholder?: string;
  filterPlaceholder?: string;
  actions?: SearchListAction<T>[];
  onQueryChange?: (query: string) => void;
  initialSelectedIndex?: number;
}

function computeVisibleCount(): number {
  return Math.max(3, (process.stdout.rows ?? 24) - 9);
}

export function SearchList<T>({
  title,
  options,
  onSelect,
  onClose,
  placeholder,
  filterPlaceholder = 'Search',
  actions = [],
  onQueryChange,
  initialSelectedIndex = 0,
}: SearchListProps<T>): React.JSX.Element {
  const { theme } = useTheme();
  const filter = useTextBuffer('');
  const [selected, setSelected] = useState(initialSelectedIndex);
  const [actionIndex, setActionIndex] = useState<number | null>(null);
  const [visibleCount, setVisibleCount] = useState(computeVisibleCount);

  useEffect(() => {
    const onResize = () => setVisibleCount(computeVisibleCount());
    process.stdout.on('resize', onResize);
    return () => {
      process.stdout.off('resize', onResize);
    };
  }, []);

  const filtered = useMemo(() => {
    const needle = filter.value.trim().toLowerCase();
    if (!needle) return options;
    return options
      .map((option) => ({
        option,
        score: fuzzyScore(needle, option.title, option.category),
      }))
      .filter((item): item is { option: SearchListOption<T>; score: number } => item.score !== null)
      .sort((a, b) => b.score - a.score)
      .map((item) => item.option);
  }, [options, filter.value]);

  const grouped = useMemo(() => {
    if (filter.value.trim()) return [{ category: '', options: filtered }];
    const groups = new Map<string, SearchListOption<T>[]>();
    for (const option of filtered) {
      const category = option.category ?? '';
      const list = groups.get(category) ?? [];
      list.push(option);
      groups.set(category, list);
    }
    return Array.from(groups.entries()).map(([category, list]) => ({ category, options: list }));
  }, [filtered, filter.value]);

  const flat = useMemo(() => filtered, [filtered]);

  const clampSelected = useCallback(
    (index: number) => {
      const max = Math.max(0, flat.length - 1);
      return Math.max(0, Math.min(index, max));
    },
    [flat.length],
  );

  const visibleWindow = useMemo(() => {
    const count = Math.min(visibleCount, flat.length);
    if (flat.length === 0) return { start: 0, end: 0 };
    const start = Math.max(0, Math.min(selected - Math.floor(count / 2), flat.length - count));
    return { start, end: start + count };
  }, [flat.length, selected, visibleCount]);

  const select = useCallback(
    (index: number) => {
      const option = flat[index];
      if (!option || option.disabled) return;
      option.onSelect?.();
      onSelect(option);
    },
    [flat, onSelect],
  );

  useInput((char, key) => {
    if (key.escape) {
      onClose();
      return;
    }

    if (key.upArrow) {
      setActionIndex(null);
      setSelected((s) => clampSelected(s - 1));
      return;
    }
    if (key.downArrow) {
      setActionIndex(null);
      setSelected((s) => clampSelected(s + 1));
      return;
    }
    if (key.pageUp) {
      setActionIndex(null);
      setSelected((s) => clampSelected(s - 10));
      return;
    }
    if (key.pageDown) {
      setActionIndex(null);
      setSelected((s) => clampSelected(s + 10));
      return;
    }
    if (key.home) {
      setActionIndex(null);
      setSelected(0);
      return;
    }
    if (key.end) {
      setActionIndex(null);
      setSelected(flat.length - 1);
      return;
    }

    if (key.return) {
      if (actionIndex !== null) {
        const action = actions[actionIndex];
        const option = flat[selected];
        if (action && option) action.onTrigger(option);
        return;
      }
      select(selected);
      return;
    }

    if (key.tab) {
      if (actions.length === 0) return;
      setActionIndex((current) => {
        if (current === null) return 0;
        return (current + 1) % actions.length;
      });
      return;
    }
    if (key.shift && key.tab) {
      if (actions.length === 0) return;
      setActionIndex((current) => {
        if (current === null) return actions.length - 1;
        return (current - 1 + actions.length) % actions.length;
      });
      return;
    }

    if (key.leftArrow || key.rightArrow || key.delete || key.backspace || char) {
      filter.handleKey(char, key);
      setActionIndex(null);
      setSelected(0);
      onQueryChange?.(filter.value);
    }
  });

  const renderOptionRow = (option: SearchListOption<T>, index: number, groupHeader = false) => {
    const isSelected = index === selected && !groupHeader;
    const isActionFocused = actionIndex !== null;
    const titleColor = option.disabled
      ? theme.colors.text.dim
      : isSelected && !isActionFocused
        ? theme.colors.status.success
        : option.current
          ? theme.colors.status.info
          : theme.colors.text.ethereal;

    return (
      <Box key={index} flexDirection="row" alignItems="center" marginTop={groupHeader ? 1 : 0} paddingLeft={2}>
        <Box width={2} flexShrink={0}>
          <Text color={theme.colors.text.muted}>{isSelected && !isActionFocused ? '▸' : ' '}</Text>
        </Box>
        {option.current && !option.gutter ? (
          <Text color={theme.colors.status.info}>● </Text>
        ) : option.gutter ? (
          <Text color={theme.colors.status.success}>{option.gutter} </Text>
        ) : null}
        <Text color={titleColor} bold={isSelected && !isActionFocused} wrap="truncate-end">
          {option.title}
        </Text>
        {option.description && (
          <Text color={theme.colors.text.muted} wrap="truncate-end">
            {' '}
            {option.description}
          </Text>
        )}
        {option.footer && (
          <Text color={theme.colors.text.muted} wrap="truncate-end">
            {' '}
            {option.footer}
          </Text>
        )}
      </Box>
    );
  };

  const rows: React.ReactNode[] = [];
  if (filter.value.trim()) {
    for (let i = visibleWindow.start; i < visibleWindow.end; i++) {
      const option = flat[i];
      rows.push(renderOptionRow(option, i));
    }
  } else {
    let flatIndex = 0;
    for (const group of grouped) {
      if (group.category && flatIndex <= visibleWindow.end) {
        rows.push(
          <Box key={`header-${group.category}`} paddingLeft={1} marginTop={1}>
            <Text color={theme.colors.status.accent} bold>
              {group.category}
            </Text>
          </Box>,
        );
      }
      for (const option of group.options) {
        if (flatIndex >= visibleWindow.start && flatIndex < visibleWindow.end) {
          rows.push(renderOptionRow(option, flatIndex));
        }
        flatIndex++;
      }
    }
  }

  return (
    <Box flexDirection="column" width="100%">
      <Box flexDirection="row" justifyContent="space-between" paddingLeft={2} paddingRight={2}>
        <Text color={theme.colors.text.ethereal} bold>
          {title}
        </Text>
        <Text color={theme.colors.text.muted}>esc</Text>
      </Box>
      <Box paddingLeft={2} paddingRight={2} marginTop={1}>
        <Text color={theme.colors.text.muted}>▸ </Text>
        <Text color={theme.colors.text.ethereal}>
          {filter.value.slice(0, filter.cursor)}
          <Text color={theme.colors.status.accent} inverse>
            {filter.value[filter.cursor] ?? ' '}
          </Text>
          {filter.value.slice(filter.cursor + 1)}
        </Text>
        <Text color={theme.colors.text.dim}> {filter.value ? '' : filterPlaceholder}</Text>
      </Box>
      <Box flexDirection="column" marginTop={1} minHeight={1}>
        {rows.length === 0 ? (
          <Box paddingLeft={3}>
            <Text color={theme.colors.text.muted}>No results found</Text>
          </Box>
        ) : (
          rows
        )}
      </Box>
      {(placeholder || actions.length > 0) && (
        <Box flexDirection="row" justifyContent="space-between" marginTop={1} paddingLeft={2} paddingRight={2}>
          <Text color={theme.colors.text.muted}>{placeholder && <Text italic>{placeholder}</Text>}</Text>
          <Box flexDirection="row" gap={1}>
            {actions.map((action, i) => {
              const isFocused = actionIndex === i;
              return (
                <Box key={action.label} flexDirection="row">
                  <Text
                    color={isFocused ? theme.colors.status.success : theme.colors.text.ethereal}
                    bold={isFocused}
                    backgroundColor={isFocused ? theme.colors.bg.modal : undefined}
                  >
                    {action.label}
                  </Text>
                  <Text color={theme.colors.text.muted}>{isFocused ? ' ⏎' : ''}</Text>
                </Box>
              );
            })}
          </Box>
        </Box>
      )}
    </Box>
  );
}
