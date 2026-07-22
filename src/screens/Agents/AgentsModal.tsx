import { Box, Text, useInput } from 'ink';
import React from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { useTheme } from '../../theme/ThemeContext';

interface AgentsModalProps {
  onClose: () => void;
}

const AGENTS = [
  {
    name: 'Frontend UX Audit Agent',
    skill: 'frontend_ux_audit',
    status: '[ACTIVE]',
    desc: 'TUI architecture & visual polish',
  },
  {
    name: 'Code Architect Agent',
    skill: 'code_architect',
    status: '[ACTIVE]',
    desc: 'System modularity & tier decoupling',
  },
  {
    name: 'Test Runner Agent',
    skill: 'test_runner',
    status: '[ACTIVE]',
    desc: 'Vitest assertion & test suite validation',
  },
];

export const AgentsModal: React.FC<AgentsModalProps> = ({ onClose }) => {
  const { theme } = useTheme();

  useInput((_char, key) => {
    if (key.escape || key.return) {
      onClose();
    }
  });

  return (
    <RoundedBox title="ACTIVE AGENTS & CAPABILITIES" borderColor={theme.colors.border.active} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        <Box marginBottom={1}>
          <Text color={theme.colors.text.emerald} bold>
            [REGISTERED AGENT SPECIFICATIONS]
          </Text>
        </Box>

        {AGENTS.map((agent, idx) => (
          <Box key={idx} flexDirection="row" alignItems="center" marginY={1} width="100%">
            <Box width={26}>
              <Text color={theme.colors.text.bright} bold>
                {agent.name}
              </Text>
            </Box>
            <Box width={20}>
              <Text color={theme.colors.status.info}>{agent.skill}</Text>
            </Box>
            <Box width={12}>
              <Text color={theme.colors.status.success}>{agent.status}</Text>
            </Box>
            <Box flexShrink={1}>
              <Text color={theme.colors.text.muted}>{agent.desc}</Text>
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
