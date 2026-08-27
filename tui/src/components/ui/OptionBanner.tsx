import { Box, Text, useInput } from 'ink';
import React, { useCallback, useEffect, useState } from 'react';
import { useTheme } from '../../theme/ThemeContext';

export interface OptionBannerOption<T = string> {
  label: string;
  value: T;
  description?: string;
}

interface OptionBannerProps<T = string> {
  title: string;
  message?: string;
  options: OptionBannerOption<T>[];
  onSelect: (value: T) => void;
  onClose: () => void;
  initialIndex?: number;
}

export function OptionBanner<T = string>({
  title,
  message,
  options,
  onSelect,
  onClose,
  initialIndex = 0,
}: OptionBannerProps<T>): React.JSX.Element {
  const { theme } = useTheme();
  const [index, setIndex] = useState(() => Math.max(0, Math.min(initialIndex, options.length - 1)));

  useEffect(() => {
    setIndex((current) => Math.max(0, Math.min(current, options.length - 1)));
  }, [options.length]);

  const move = useCallback(
    (delta: number) => {
      setIndex((current) => (current + delta + options.length) % options.length);
    },
    [options.length],
  );

  useInput(
    (_input, key) => {
      if (key.leftArrow) {
        move(-1);
        return;
      }
      if (key.rightArrow) {
        move(1);
        return;
      }
      if (key.return) {
        const option = options[index];
        if (option) onSelect(option.value);
        return;
      }
      if (key.escape) {
        onClose();
      }
    },
    { isActive: true },
  );

  return (
    <Box flexDirection="row" width="100%" alignItems="center" marginBottom={1}>
      <Box
        flexDirection="row"
        width="100%"
        alignItems="center"
        borderStyle="single"
        borderColor={theme.colors.status.warning}
        paddingX={1}
        paddingY={0}
      >
        <Text color={theme.colors.status.warning} bold>
          {title}{' '}
        </Text>
        {message && (
          <Text color={theme.colors.text.bright} wrap="truncate-end">
            {message}
          </Text>
        )}
        <Box flexDirection="row" gap={1} marginLeft={1} flexShrink={0}>
          {options.map((option, i) => {
            const isSelected = i === index;
            return (
              <Box key={option.label} flexDirection="row" alignItems="center">
                <Text
                  color={isSelected ? theme.colors.status.success : theme.colors.text.ethereal}
                  bold={isSelected}
                  backgroundColor={isSelected ? theme.colors.bg.modal : undefined}
                >
                  {isSelected ? '▸ ' : '  '}
                  {option.label}
                </Text>
                {isSelected && <Text color={theme.colors.text.muted}> ⏎</Text>}
              </Box>
            );
          })}
        </Box>
        <Box flexGrow={1} />
        <Text color={theme.colors.text.dim}>←→ · esc</Text>
      </Box>
    </Box>
  );
}
