import type React from 'react';
import type { ScenarioEvent, TurnManifestEvent } from '../../../types/scenario';
import { CaptainOrchestratorBlock } from './CaptainOrchestratorBlock';
import { CompactionFlowBlock } from './CompactionFlowBlock';
import { ErrorBlock } from './ErrorBlock';
import { FinalSummaryCard } from './FinalSummaryCard';
import { MessageBlock } from './MessageBlock';
import { PlanReadyBlock } from './PlanReadyBlock';
import { ProgressBar } from './ProgressBar';
import { SessionStatusLine } from './SessionStatusLine';
import { SuccessCard } from './SuccessCard';
import { ThinkingBlock } from './ThinkingBlock';
import { TodoBoardBlock } from './TodoBoardBlock';
import { ToolStepCard } from './ToolStepCard';
import { ToolTraceBlock } from './ToolTraceBlock';
import { TurnManifestCard } from './TurnManifestCard';
import { UnknownEventFallback } from './UnknownEventFallback';
import { WarningBlock } from './WarningBlock';

export interface EventRenderContext {
  thinkingCollapsed?: boolean;
  calmMode?: boolean;
  isHistorical?: boolean;
  isRunning?: boolean;
  workspaceName?: string;
  gitBranch?: string;
}

export type EventComponentType = React.ComponentType<{
  event: ScenarioEvent;
  context?: EventRenderContext;
  manifest?: TurnManifestEvent;
  turnEvents?: ScenarioEvent[];
}>;

class ComponentRegistry {
  private registry: Map<string, EventComponentType> = new Map();

  constructor() {
    this.registerDefaults();
  }

  private registerDefaults() {
    this.register('thinking', ThinkingBlock as EventComponentType);
    this.register('message', MessageBlock as EventComponentType);
    this.register('tool_step', ToolStepCard as EventComponentType);
    this.register('tool_call', ToolTraceBlock as EventComponentType);
    this.register('tool_result', ToolTraceBlock as EventComponentType);
    this.register('error', ErrorBlock as EventComponentType);
    this.register('warning', WarningBlock as EventComponentType);
    this.register('success', SuccessCard as EventComponentType);
    this.register('progress', ProgressBar as EventComponentType);
    this.register('plan_ready', PlanReadyBlock as EventComponentType);
    this.register('turn_manifest', TurnManifestCard as EventComponentType);
    this.register('captain_orchestration', CaptainOrchestratorBlock as EventComponentType);
    this.register('todo_board', TodoBoardBlock as unknown as EventComponentType);
    this.register('context_compaction_flow', CompactionFlowBlock as EventComponentType);
    // Session/context/token housekeeping events render as dim status lines.
    this.register('session_created', SessionStatusLine as unknown as EventComponentType);
    this.register('session_resumed', SessionStatusLine as unknown as EventComponentType);
    this.register('session_state_changed', SessionStatusLine as unknown as EventComponentType);
    this.register('session_paused', SessionStatusLine as unknown as EventComponentType);
    this.register('session_renamed', SessionStatusLine as unknown as EventComponentType);
    this.register('session_error', SessionStatusLine as unknown as EventComponentType);
    this.register('session_status', SessionStatusLine as unknown as EventComponentType);
    this.register('session_summarized', FinalSummaryCard as unknown as EventComponentType);
    this.register('context_updated', SessionStatusLine as unknown as EventComponentType);
    this.register('token_usage_recorded', SessionStatusLine as unknown as EventComponentType);
  }

  public register(kind: string, component: EventComponentType): void {
    this.registry.set(kind, component);
  }

  public getComponent(kind: string): EventComponentType {
    return this.registry.get(kind) || (UnknownEventFallback as EventComponentType);
  }
}

export const componentRegistry = new ComponentRegistry();
