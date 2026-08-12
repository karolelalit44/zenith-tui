import type React from 'react';
import type { ScenarioEvent, TurnManifestEvent } from '../../../types/scenario';
import { ContextStatusBlock } from './ContextStatusBlock';
import { ErrorBlock } from './ErrorBlock';
import { MessageBlock } from './MessageBlock';
import { PlanReadyBlock } from './PlanReadyBlock';
import { ProgressBar } from './ProgressBar';
import { SuccessCard } from './SuccessCard';
import { ThinkingBlock } from './ThinkingBlock';
import { ToolStepCard } from './ToolStepCard';
import { ToolTraceBlock } from './ToolTraceBlock';
import { TurnManifestCard } from './TurnManifestCard';
import { UnknownEventFallback } from './UnknownEventFallback';
import { WarningBlock } from './WarningBlock';

export interface EventRenderContext {
  thinkingCollapsed?: boolean;
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
    this.register('context_compacted', ContextStatusBlock as EventComponentType);
    this.register('context_compaction_started', ContextStatusBlock as EventComponentType);
    this.register('context_compaction_ended', ContextStatusBlock as EventComponentType);
  }

  public register(kind: string, component: EventComponentType): void {
    this.registry.set(kind, component);
  }

  public getComponent(kind: string): EventComponentType {
    return this.registry.get(kind) || (UnknownEventFallback as EventComponentType);
  }
}

export const componentRegistry = new ComponentRegistry();
