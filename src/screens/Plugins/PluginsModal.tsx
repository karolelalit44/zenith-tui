import { Box, Text, useInput } from 'ink';
import React from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { useTheme } from '../../theme/ThemeContext';

interface PluginsModalProps {
  onClose: () => void;
}

const PLUGINS = [
  { name: 'Dracula Syntax Highlighter', version: 'v1.4.0', type: 'Theme / Formatting', status: '[LOADED]' },
  { name: 'VT/SGR Terminal Viewport Scroller', version: 'v2.1.0', type: 'Terminal Driver', status: '[LOADED]' },
  { name: 'Markdown Implementation Plan Exporter', version: 'v1.0.0', type: 'Export Extension', status: '[LOADED]' },
];

export const PluginsModal: React.FC<PluginsModalProps> = ({ onClose }) => {
  const { theme } = useTheme();

  useInput((_char, key) => {
    if (key.escape || key.return) {
      onClose();
    }
  });

  return (
    <RoundedBox title="ZENITH PLUGINS & EXTENSIONS" borderColor={theme.colors.border.active} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        <Box marginBottom={1}>
          <Text color={theme.colors.text.emerald} bold>
            [INSTALLED ZENITH EXTENSIONS]
          </Text>
        </Box>

        {PLUGINS.map((plug, idx) => (
          <Box key={idx} flexDirection="row" alignItems="center" marginY={1} width="100%">
            <Box width={38}>
              <Text color={theme.colors.text.bright} bold>
                {plug.name}
              </Text>
            </Box>
            <Box width={12}>
              <Text color={theme.colors.text.muted}>{plug.version}</Text>
            </Box>
            <Box width={12}>
              <Text color={theme.colors.status.success}>{plug.status}</Text>
            </Box>
            <Box flexShrink={1}>
              <Text color={theme.colors.text.muted}>{plug.type}</Text>
            </Box>
          </Box>
        ))}

        <Box marginTop={1} paddingTop={1} borderStyle="single" borderTop={true} borderColor={theme.colors.border.muted}>
          <Text color={theme.colors.text.muted}>
            Press <Text color={theme.colors.text.emerald}>[Esc]</Text> to close
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
