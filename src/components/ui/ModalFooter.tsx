import { Text } from 'ink';
import React from 'react';
import { useTheme } from '../../theme/ThemeContext';

interface Shortcut {
  key: string;
  label: string;
}

interface ModalFooterProps {
  shortcuts: Shortcut[];
}

export const ModalFooter: React.FC<ModalFooterProps> = ({ shortcuts }) => {
  const { theme } = useTheme();
  return (
    <Text>
      {shortcuts.map((s, i) => (
        <Text key={i}>
          {i > 0 && <Text> · </Text>}
          <Text color={theme.colors.text.emerald}>{s.key}</Text> {s.label}
        </Text>
      ))}
    </Text>
  );
};
