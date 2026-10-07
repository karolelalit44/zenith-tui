import { Box } from 'ink';
import React from 'react';
import type { CaptainOrchestrationEvent } from '../../../types/scenario';
import { type ConsolidatedOrchestration, deriveOrchestrationFlags } from '../../../utils/orchestration';
import { PinnedOrchestrationCard } from './PinnedOrchestrationCard';

interface CaptainOrchestratorBlockProps {
  event: CaptainOrchestrationEvent;
}

/**
 * Adapts a raw `captain_orchestration` event into the consolidated shape the
 * pinned card consumes. The tallies come from `deriveOrchestrationFlags` — the
 * same function `consolidateOrchestrationEvents` uses — so a mission rendered
 * inline and one rendered from the live stream cannot disagree.
 */
export const CaptainOrchestratorBlock: React.FC<CaptainOrchestratorBlockProps> = React.memo(({ event }) => {
  const normalized: ConsolidatedOrchestration = {
    ...event,
    crewmates: event.crewmates ?? [],
    ...deriveOrchestrationFlags(event.crewmates ?? []),
  };

  return (
    <Box flexDirection="column" width="100%" marginTop={1} marginBottom={1}>
      <PinnedOrchestrationCard event={normalized} isRunning={event.stage !== 'complete'} />
    </Box>
  );
});

CaptainOrchestratorBlock.displayName = 'CaptainOrchestratorBlock';
