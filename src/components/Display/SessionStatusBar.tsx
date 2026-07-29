import { Box, Text } from 'ink';
import React from 'react';
import { useScenario } from '../../hooks/useScenario';
import type { TokenUsageStats } from '../../services/data/TokenUsageService';
import type { ScenarioMode } from '../../types';

interface SessionStatusBarProps {
  mode: ScenarioMode;
  totalTokens: number;
  maxTokens?: number;
  isRunning?: boolean;
  isOverlayOpen?: boolean;
  hasEvents?: boolean;
  modelName?: string;
  workspaceName?: string;
  gitBranch?: string;
  tokenUsageStats?: TokenUsageStats | null;
}

export const SessionStatusBar: React.FC<SessionStatusBarProps> = ({
  mode,
  totalTokens,
  maxTokens,
  isRunning,
  isOverlayOpen,
  hasEvents,
  modelName,
  workspaceName,
  gitBranch,
  tokenUsageStats,
}) => {
  const { lastSessionId } = useScenario();

  const contextPercent = maxTokens && maxTokens > 0 ? Math.round((totalTokens / maxTokens) * 100) : null;
  const shortId = lastSessionId ? lastSessionId.slice(0, 8) : null;

  return (
    <Box width="100%" marginTop={1} paddingX={1} paddingY={0} borderStyle="single" borderDimColor>
      <Box flexGrow={1} flexDirection="row">
        {shortId && (
          <Text>
            <Text bold>ID:</Text> <Text color="cyan">{shortId}</Text>
            {'  '}
          </Text>
        )}
        <Text>
          <Text bold>Mode:</Text> <Text color={mode === 'plan' ? 'yellow' : 'green'}>{mode}</Text>
          {'  '}
        </Text>
        {contextPercent !== null && (
          <Text>
            <Text bold>Context:</Text>{' '}
            <Text color={contextPercent > 80 ? 'red' : contextPercent > 50 ? 'yellow' : 'white'}>
              {contextPercent}%
            </Text>
            {'  '}
          </Text>
        )}
        <Text>
          <Text bold>Tokens:</Text> <Text color="white">{totalTokens.toLocaleString()}</Text>
          {maxTokens ? <Text color="gray">/{maxTokens.toLocaleString()}</Text> : null}
          {'  '}
        </Text>
        {isRunning && <Text color="green">● Running</Text>}
        {hasEvents && !isRunning && <Text color="gray">● Idle</Text>}
        {isOverlayOpen && <Text color="yellow">● Menu</Text>}
        {modelName && (
          <Text>
            {'  '}
            <Text bold>Model:</Text> <Text color="magenta">{modelName}</Text>
          </Text>
        )}
        {workspaceName && (
          <Text>
            {'  '}
            <Text bold>CWD:</Text> <Text color="gray">{workspaceName}</Text>
          </Text>
        )}
        {gitBranch && (
          <Text>
            {'  '}
            <Text bold>Branch:</Text> <Text color="cyan">{gitBranch}</Text>
          </Text>
        )}
      </Box>
      <Box>
        {tokenUsageStats && (
          <Text color="gray">{tokenUsageStats.totals.grand_total_tokens?.toLocaleString() ?? 0} total</Text>
        )}
      </Box>
    </Box>
  );
};
