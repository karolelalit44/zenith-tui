import React from 'react';
import { Box, Text } from 'ink';
import { Mascot } from '../components/Mascot';
import { RoundedBox } from '../components/RoundedBox';
import { theme } from '../theme/theme';

export const DashboardScreen: React.FC = React.memo(() => {
  return (
    <RoundedBox title="Zenith v1.0.0" borderColor={theme.colors.border.active}>
      <Box flexDirection="row" width="100%">
        {/* Left Side */}
        <Box flexDirection="column" width="50%" paddingRight={2}>
          <Text color={theme.colors.text.primary}>Welcome back, Architect.</Text>
          <Box marginY={1} justifyContent="center">
            <Mascot color={theme.colors.text.accentOrange} />
          </Box>
          <Box justifyContent="center">
            <Text color={theme.colors.text.muted}>Model: Sonnet 4.5</Text>
          </Box>
          <Box justifyContent="center" marginTop={1}>
            <Text color={theme.colors.text.muted}>Workspace: ~/BCApps</Text>
          </Box>
        </Box>

        {/* Divider */}
        <Box width={1}>
          <Text color={theme.colors.border.muted}>│{"\n"}│{"\n"}│{"\n"}│{"\n"}│{"\n"}│{"\n"}│{"\n"}│</Text>
        </Box>

        {/* Right Side */}
        <Box flexDirection="column" width="50%" paddingLeft={2}>
          <Text color={theme.colors.text.accentOrange} bold>● Quick Start</Text>
          <Box marginTop={1} flexDirection="column">
            <Text color={theme.colors.text.primary}>Type <Text color={theme.colors.text.accentPurple}>/help</Text> for available commands.</Text>
            <Text color={theme.colors.text.primary}>Type <Text color={theme.colors.text.accentPurple}>/plugin</Text> to manage integrations.</Text>
          </Box>
          
          <Box marginTop={2} flexDirection="column">
            <Text color={theme.colors.text.accentOrange} bold>● Recent Activity</Text>
            <Box marginTop={1}>
              <Text color={theme.colors.text.muted}>No recent activity.</Text>
            </Box>
          </Box>
        </Box>
      </Box>
    </RoundedBox>
  );
});
