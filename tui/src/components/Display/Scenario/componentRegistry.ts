import type React from 'react';
import type { ScenarioEvent } from '../../../types/scenario';
import { ContextStatusBlock } from './ContextStatusBlock';
import { ErrorBlock } from './ErrorBlock';
import { MessageBlock } from './MessageBlock';
import { ProgressBar } from './ProgressBar';
import { SuccessCard } from './SuccessCard';
import { ThinkingBlock } from './ThinkingBlock';
import { ToolCallCard } from './ToolCallCard';
import { ToolResultCard } from './ToolResultCard';
import { UnknownEventFallback } from './UnknownEventFallback';
import { WarningBlock } from './WarningBlock';

export interface EventRenderContext {
  thinkingCollapsed?: boolean;
  isHistorical?: boolean;
  isRunning?: boolean;
}

export type EventComponentType = React.ComponentType<{ event: ScenarioEvent; context?: EventRenderContext }>;

class ComponentRegistry {
  private registry: Map<string, EventComponentType> = new Map();

  constructor() {
    this.registerDefaults();
  }

  private registerDefaults() {
    this.register('thinking', ThinkingBlock as EventComponentType);
    this.register('message', MessageBlock as EventComponentType);
    this.register('tool_call', ToolCallCard as EventComponentType);
    this.register('tool_result', ToolResultCard as EventComponentType);
    this.register('error', ErrorBlock as EventComponentType);
    this.register('warning', WarningBlock as EventComponentType);
    this.register('success', SuccessCard as EventComponentType);
    this.register('progress', ProgressBar as EventComponentType);
    this.register('plan_ready', MessageBlock as EventComponentType);
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
