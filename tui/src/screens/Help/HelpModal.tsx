import { Box, Text, useInput } from 'ink';
import React from 'react';
import { ModalFooter } from '../../components/ui/ModalFooter';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { formatKeyBind, KEYBINDINGS, type KeybindId, type Keybinding } from '../../config/keybind';
import { APP_VERSION } from '../../constants/app';
import { useTheme } from '../../theme/ThemeContext';

interface HelpModalProps {
  onClose: () => void;
}

const SHORTCUTS = Object.entries(KEYBINDINGS) as [KeybindId, Keybinding][];

export const HelpModal: React.FC<HelpModalProps> = ({ onClose }) => {
  const { theme } = useTheme();

  useInput((_char, key) => {
    if (key.escape || key.return) {
      onClose();
    }
  });

  const leftShortcuts = SHORTCUTS.slice(0, Math.ceil(SHORTCUTS.length / 2));
  const rightShortcuts = SHORTCUTS.slice(Math.ceil(SHORTCUTS.length / 2));

  const renderShortcutList = (entries: [KeybindId, Keybinding][]) => (
    <Box flexDirection="column" width="50%" paddingRight={1}>
      {entries.map(([id, kb]) => (
        <Box key={id} flexDirection="row">
          <Text color={theme.colors.status.info} bold>
            {formatKeyBind(id)}
          </Text>
          <Text color={theme.colors.text.muted}> {kb.description}</Text>
        </Box>
      ))}
    </Box>
  );

  return (
    <RoundedBox title="ZENITH HELP & KEYBOARD SHORTCUTS" borderColor={theme.colors.border.active} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        {}
        <Box marginBottom={1} flexDirection="row" justifyContent="space-between" alignItems="center">
          <Text color={theme.colors.text.emerald} bold>
            [HELP & CLI WORKFLOW GUIDE]
          </Text>
          <Text color={theme.colors.text.muted}>Press Esc or Enter to close</Text>
        </Box>

        {}
        <Text color={theme.colors.text.warning} bold underline>
          KEYBOARD SHORTCUTS
        </Text>
        <Box marginTop={1} flexDirection="row" width="100%">
          {renderShortcutList(leftShortcuts)}
          {renderShortcutList(rightShortcuts)}
        </Box>

        <Box
          marginTop={1}
          paddingTop={1}
          borderStyle="single"
          borderTop={true}
          borderBottom={false}
          borderLeft={false}
          borderRight={false}
          borderColor={theme.colors.border.muted}
        />

        <Box flexDirection="row" width="100%" justifyContent="space-between">
          {}
          <Box flexDirection="column" width="50%">
            <Text color={theme.colors.text.warning} bold underline>
              SLASH COMMANDS
            </Text>
            <Box marginTop={1} flexDirection="column">
              <Text color={theme.colors.text.ethereal}>
                <Text color={theme.colors.status.success}>/provider</Text> AI Provider Management
              </Text>
              <Text color={theme.colors.text.ethereal}>
                <Text color={theme.colors.status.success}>/settings</Text> Theme & Options
              </Text>
              <Text color={theme.colors.text.ethereal}>
                <Text color={theme.colors.status.success}>/context</Text> View Context Window
              </Text>
              <Text color={theme.colors.text.ethereal}>
                <Text color={theme.colors.status.success}>/clear</Text> Reset Conversation
              </Text>
              <Text color={theme.colors.text.ethereal}>
                <Text color={theme.colors.status.success}>/compact</Text> Compress History
              </Text>
              <Text color={theme.colors.text.ethereal}>
                <Text color={theme.colors.status.success}>/model</Text> Open Model Picker
              </Text>
              <Text color={theme.colors.text.ethereal}>
                <Text color={theme.colors.status.success}>/session</Text> Browse & Resume Sessions
              </Text>
              <Text color={theme.colors.text.ethereal}>
                <Text color={theme.colors.status.success}>/exit</Text> Save & Exit Zenith
              </Text>
            </Box>
          </Box>

          <Box width={1}>
            <Text color={theme.colors.border.muted}>│</Text>
          </Box>

          {}
          <Box flexDirection="column" width="48%">
            <Text color={theme.colors.text.warning} bold underline>
              OPERATING MODES
            </Text>
            <Box marginTop={1} flexDirection="column">
              <Text color={theme.colors.status.accent} bold>
                [PLAN MODE]
              </Text>
              <Text color={theme.colors.text.muted}>
                Generates architectural roadmaps and saves to zenith_plans/ (created on first save).
              </Text>

              <Box marginTop={1}>
                <Text color={theme.colors.status.success} bold>
                  [BUILD MODE]
                </Text>
              </Box>
              <Text color={theme.colors.text.muted}>Executes code generation, tests, and terminal build steps.</Text>
            </Box>
          </Box>
        </Box>

        <Box
          marginTop={1}
          paddingTop={1}
          borderStyle="single"
          borderTop={true}
          borderBottom={false}
          borderLeft={false}
          borderRight={false}
          borderColor={theme.colors.border.muted}
          justifyContent="center"
        >
          <Text color={theme.colors.text.muted}>
            Zenith TUI v{APP_VERSION} · <ModalFooter shortcuts={[{ key: '[Esc]', label: 'to return to prompt' }]} />
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
