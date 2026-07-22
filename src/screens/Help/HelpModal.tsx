import { Box, Text, useInput } from 'ink';
import React from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { useTheme } from '../../theme/ThemeContext';

interface HelpModalProps {
  onClose: () => void;
}

export const HelpModal: React.FC<HelpModalProps> = ({ onClose }) => {
  const { theme } = useTheme();

  useInput((_char, key) => {
    if (key.escape || key.return) {
      onClose();
    }
  });

  return (
    <RoundedBox title="ZENITH HELP & KEYBOARD SHORTCUTS" borderColor={theme.colors.border.active} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        {/* Header banner */}
        <Box marginBottom={1} flexDirection="row" justifyContent="space-between" alignItems="center">
          <Text color={theme.colors.text.emerald} bold>
            [HELP & CLI WORKFLOW GUIDE]
          </Text>
          <Text color={theme.colors.text.muted}>Press Esc or Enter to close</Text>
        </Box>

        <Box flexDirection="row" width="100%" justifyContent="space-between">
          {/* Column 1: Keyboard Shortcuts */}
          <Box flexDirection="column" width="30%">
            <Text color={theme.colors.text.warning} bold underline>
              KEYBOARD SHORTCUTS
            </Text>
            <Box marginTop={1} flexDirection="column">
              <Box flexDirection="row">
                <Text color={theme.colors.status.info} bold>
                  Shift + M
                </Text>
                <Text color={theme.colors.text.muted}> Switch Mode</Text>
              </Box>
              <Box flexDirection="row">
                <Text color={theme.colors.status.info} bold>
                  Ctrl + S
                </Text>
                <Text color={theme.colors.text.muted}> Save Plan</Text>
              </Box>
              <Box flexDirection="row">
                <Text color={theme.colors.status.info} bold>
                  Shift + T
                </Text>
                <Text color={theme.colors.text.muted}> Toggle Thinking</Text>
              </Box>
              <Box flexDirection="row">
                <Text color={theme.colors.status.info} bold>
                  Esc
                </Text>
                <Text color={theme.colors.text.muted}> Cancel / Exit</Text>
              </Box>
              <Box flexDirection="row">
                <Text color={theme.colors.status.info} bold>
                  @
                </Text>
                <Text color={theme.colors.text.muted}> File Picker</Text>
              </Box>
              <Box flexDirection="row">
                <Text color={theme.colors.status.info} bold>
                  /
                </Text>
                <Text color={theme.colors.text.muted}> Command Palette</Text>
              </Box>
            </Box>
          </Box>

          <Box width={1}>
            <Text color={theme.colors.border.muted}>│</Text>
          </Box>

          {/* Column 2: Slash Commands */}
          <Box flexDirection="column" width="34%">
            <Text color={theme.colors.text.warning} bold underline>
              SLASH COMMANDS
            </Text>
            <Box marginTop={1} flexDirection="column">
              <Text color={theme.colors.text.ethereal}>
                <Text color={theme.colors.status.success}>/mode</Text> Switch Build / Plan
              </Text>
              <Text color={theme.colors.text.ethereal}>
                <Text color={theme.colors.status.success}>/persona</Text> Change Agent Persona
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
            </Box>
          </Box>

          <Box width={1}>
            <Text color={theme.colors.border.muted}>│</Text>
          </Box>

          {/* Column 3: Workflow Tips */}
          <Box flexDirection="column" width="32%">
            <Text color={theme.colors.text.warning} bold underline>
              OPERATING MODES
            </Text>
            <Box marginTop={1} flexDirection="column">
              <Text color={theme.colors.status.accent} bold>
                [PLAN MODE]
              </Text>
              <Text color={theme.colors.text.muted}>Generates architectural roadmaps and saves to zenith_plans/.</Text>

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
          borderColor={theme.colors.border.muted}
          justifyContent="center"
        >
          <Text color={theme.colors.text.muted}>
            Zenith TUI v1.0.0 · Press <Text color={theme.colors.status.info}>[Esc]</Text> to return to prompt
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
