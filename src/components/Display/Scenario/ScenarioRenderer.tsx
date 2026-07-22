import React, { useState, useEffect } from 'react';
import { Box, Text, useInput } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { ScenarioEvent } from '../../../types/scenario';
import { ThinkingBlock } from './ThinkingBlock';
import { FileDiffCard } from './FileDiffCard';
import { FileEditDiffCard } from './FileEditDiffCard';
import { FileDeleteCard } from './FileDeleteCard';
import { TerminalBlock } from './TerminalBlock';
import { ErrorBlock } from './ErrorBlock';
import { WarningBlock } from './WarningBlock';
import { RetryBlock } from './RetryBlock';
import { SuccessCard } from './SuccessCard';
import { SummaryCard } from './SummaryCard';
import { MessageBlock } from './MessageBlock';
import { ProgressBar } from './ProgressBar';
import { WaitingIndicator } from './WaitingIndicator';
import { TestExecutionCard } from './TestExecutionCard';
import { BuildStepCard } from './BuildStepCard';
import { DeploymentCard } from './DeploymentCard';
import { AnalysisCard } from './AnalysisCard';
import { PlannerActionPanel } from './PlannerActionPanel';
import { ModeMismatchView } from './ModeMismatchView';

interface ScenarioRendererProps {
  events: ScenarioEvent[];
  isRunning: boolean;
  isHistorical?: boolean;
  currentThinkingPhase?: string;
}

const LiveSpinner: React.FC<{ label: string }> = React.memo(({ label }) => {
  const [spinnerTick, setSpinnerTick] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setSpinnerTick(t => t + 1), 100);
    return () => clearInterval(interval);
  }, []);

  const spinnerFrames = ['|', '/', '-', '\\'];

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" flexWrap="wrap">
        <Text color="#58A6FF" bold>[IN PROGRESS] </Text>
        <Text color="#3FB950" bold>{spinnerFrames[spinnerTick % 4]} </Text>
        <Text color="#E6EDF3" bold>{label}</Text>
        <Text color="#8B949E"> (Press ESC to cancel)</Text>
      </Box>
    </Box>
  );
});

export const ScenarioRenderer: React.FC<ScenarioRendererProps> = React.memo(({
  events,
  isRunning,
  isHistorical = false,
}) => {
  const [thinkingVisible, setThinkingVisible] = useState(true);

  useInput((char, key) => {
    if (key.shift && (char === 't' || char === 'T')) {
      setThinkingVisible(prev => !prev);
    }
  });

  const lastEvent = events[events.length - 1];
  const showLiveIndicator = isRunning && !isHistorical && lastEvent?.kind === 'thinking';

  return (
    <Box flexDirection="column" width="100%">
      {events.map((event) => {
        switch (event.kind) {
          case 'thinking':
            return (
              <ThinkingBlock
                key={event.id}
                event={event}
                collapsed={!thinkingVisible}
                onToggle={() => setThinkingVisible(v => !v)}
                isHistorical={isHistorical}
              />
            );
          case 'file_create':
            return <FileDiffCard key={event.id} event={event} isHistorical={isHistorical} />;
          case 'file_edit':
            return <FileEditDiffCard key={event.id} event={event} isHistorical={isHistorical} />;
          case 'file_delete':
            return <FileDeleteCard key={event.id} event={event} />;
          case 'terminal':
            return <TerminalBlock key={event.id} event={event} isHistorical={isHistorical} />;
          case 'error':
            return <ErrorBlock key={event.id} event={event} />;
          case 'warning':
            return <WarningBlock key={event.id} event={event} />;
          case 'retry':
            return <RetryBlock key={event.id} event={event} />;
          case 'success':
            return <SuccessCard key={event.id} event={event} />;
          case 'summary':
            return <SummaryCard key={event.id} event={event} />;
          case 'message':
            return <MessageBlock key={event.id} event={event} />;
          case 'progress':
            return <ProgressBar key={event.id} event={event} />;
          case 'waiting':
            return <WaitingIndicator key={event.id} event={event} />;
          case 'test_execution':
            return <TestExecutionCard key={event.id} event={event} />;
          case 'build_step':
            return <BuildStepCard key={event.id} event={event} />;
          case 'deployment':
            return <DeploymentCard key={event.id} event={event} />;
          case 'analysis':
            return <AnalysisCard key={event.id} event={event} />;
          case 'planner_action_panel':
            return <PlannerActionPanel key={event.id} event={event} />;
          case 'mode_mismatch':
            return <ModeMismatchView key={event.id} event={event} />;
          default:
            return null;
        }
      })}

      {isRunning && !isHistorical && events.length === 0 && (
        <LiveSpinner label="Thinking..." />
      )}

      {showLiveIndicator && (
        <LiveSpinner label="Processing..." />
      )}
    </Box>
  );
});
