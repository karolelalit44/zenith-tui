import type React from 'react';
import type { ScenarioEvent } from '../../../types/scenario';
import { AnalysisCard } from './AnalysisCard';
import { BuildStepCard } from './BuildStepCard';
import { DeploymentCard } from './DeploymentCard';
import { ErrorBlock } from './ErrorBlock';
import { FileDeleteCard } from './FileDeleteCard';
import { FileDiffCard } from './FileDiffCard';
import { FileEditDiffCard } from './FileEditDiffCard';
import { MessageBlock } from './MessageBlock';
import { ModeMismatchView } from './ModeMismatchView';
import { PlannerActionPanel } from './PlannerActionPanel';
import { ProgressBar } from './ProgressBar';
import { RetryBlock } from './RetryBlock';
import { SuccessCard } from './SuccessCard';
import { SummaryCard } from './SummaryCard';
import { TerminalBlock } from './TerminalBlock';
import { TestExecutionCard } from './TestExecutionCard';
import { ThinkingBlock } from './ThinkingBlock';
import { UnknownEventFallback } from './UnknownEventFallback';
import { WaitingIndicator } from './WaitingIndicator';
import { WarningBlock } from './WarningBlock';

/**
 * Standard Production Render Context passed uniformly to all registered event components.
 * No component-specific branching required in the renderer dispatcher loop.
 */
export interface EventRenderContext {
  thinkingCollapsed?: boolean;
  isHistorical?: boolean;
  isRunning?: boolean;
}

export interface EventComponentProps<T extends ScenarioEvent = ScenarioEvent> {
  event: T;
  context?: EventRenderContext;
}

export type EventComponentType = React.ComponentType<EventComponentProps<any>>;

class ComponentRegistry {
  private registry: Map<string, EventComponentType> = new Map();

  constructor() {
    this.registerDefaults();
  }

  private registerDefaults() {
    this.register('thinking', ThinkingBlock as EventComponentType);
    this.register('file_create', FileDiffCard as EventComponentType);
    this.register('file_edit', FileEditDiffCard as EventComponentType);
    this.register('file_delete', FileDeleteCard as EventComponentType);
    this.register('terminal', TerminalBlock as EventComponentType);
    this.register('error', ErrorBlock as EventComponentType);
    this.register('warning', WarningBlock as EventComponentType);
    this.register('retry', RetryBlock as EventComponentType);
    this.register('success', SuccessCard as EventComponentType);
    this.register('summary', SummaryCard as EventComponentType);
    this.register('message', MessageBlock as EventComponentType);
    this.register('progress', ProgressBar as EventComponentType);
    this.register('waiting', WaitingIndicator as EventComponentType);
    this.register('test_execution', TestExecutionCard as EventComponentType);
    this.register('build_step', BuildStepCard as EventComponentType);
    this.register('deployment', DeploymentCard as EventComponentType);
    this.register('analysis', AnalysisCard as EventComponentType);
    this.register('planner_action_panel', PlannerActionPanel as EventComponentType);
    this.register('mode_mismatch', ModeMismatchView as EventComponentType);
  }

  public register(kind: string, component: EventComponentType): void {
    this.registry.set(kind, component);
  }

  public getComponent(kind: string): EventComponentType {
    return this.registry.get(kind) || (UnknownEventFallback as EventComponentType);
  }
}

export const componentRegistry = new ComponentRegistry();
