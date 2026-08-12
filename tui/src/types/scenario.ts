export type EventKind =
  | 'thinking'
  | 'message'
  | 'tool_call'
  | 'tool_result'
  | 'tool_step'
  | 'error'
  | 'warning'
  | 'success'
  | 'progress'
  | 'plan_ready'
  | 'context_compacted'
  | 'context_compaction_started'
  | 'context_compaction_ended'
  | 'agent_orchestration';

export interface ThinkingThought {
  text: string;
  delay?: number;
}

export interface ThinkingEvent {
  kind: 'thinking';
  id: string;
  thoughts: string[] | ThinkingThought[];
  duration: number;
}

export interface FileLine {
  text: string;
  type: 'add' | 'remove' | 'context';
  highlighted?: boolean;
}

export interface ErrorEvent {
  kind: 'error';
  id: string;
  message: string;
  code?: string;
  recoverable?: boolean;
  provider?: string;
  action?: string;
  hint?: string;
}

export interface WarningEvent {
  kind: 'warning';
  id: string;
  message: string;
  code?: string;
}

export interface TokenInfo {
  used: number;
  remaining: number;
  total: number;
  percent: number;
}

export interface SuccessEvent {
  kind: 'success';
  id: string;
  message: string;
  iterations?: number;
  tokenInfo?: TokenInfo;
  elapsedMs?: number;
}

export interface MessageEvent {
  kind: 'message';
  id: string;
  text: string;
  partial?: boolean;
  iteration?: number;
}

export interface ToolCallEvent {
  kind: 'tool_call';
  id: string;
  tool: string;
  params: Record<string, unknown>;
  text?: string;
}

export interface ToolResultEvent {
  kind: 'tool_result';
  id: string;
  tool: string;
  success: boolean;
  output: string;
  error: string;
  truncated?: boolean;
  metadata: Record<string, unknown>;
}

export interface ToolStepEvent {
  kind: 'tool_step';
  id: string;
  tool: string;
  params: Record<string, unknown>;
  success: boolean;
  output: string;
  error: string;
  truncated?: boolean;
  metadata: Record<string, unknown>;
  text?: string;
  pending: boolean;
}

export interface ProgressEvent {
  kind: 'progress';
  id: string;
  label: string;
  steps: { label: string; status: 'pending' | 'active' | 'done' | 'error' }[];
  percent?: number;
  iteration?: number;
}

export interface PlanReadyEvent {
  kind: 'plan_ready';
  id: string;
  plan: string;
  sessionId: string;
}

export interface ContextCompactedEvent {
  kind: 'context_compacted';
  id: string;
  message: string;
  tool?: string;
  tokensSaved?: number;
}

export interface ContextCompactionStartedEvent {
  kind: 'context_compaction_started';
  id: string;
  message: string;
  used?: number;
  total?: number;
}

export interface ContextCompactionEndedEvent {
  kind: 'context_compaction_ended';
  id: string;
  message: string;
  tokensSaved?: number;
  summaryChars?: number;
}

export interface TurnManifestEvent {
  kind: 'turn_manifest';
  id: string;
  created: string[];
  modified: string[];
  remaining: string[];
  completed: boolean;
  stalled: boolean;
  files: { path: string; exists: boolean; size: number }[];
}

export type CrewmateStatus =
  | 'spawned'
  | 'assigned'
  | 'working'
  | 'completed'
  | 'needs_review'
  | 'failed'
  | 'reassigned'
  | 'returning'
  | 'reviewed'
  | 'retired';

export interface CrewmateAgent {
  id: string;
  name: string;
  role: string;
  task: string;
  activity?: string;
  status: CrewmateStatus;
  progress?: number;
  resultSummary?: string;
  error?: string;
}

export type PlanItemStatus =
  | 'queued'
  | 'in_progress'
  | 'completed'
  | 'needs_review'
  | 'failed'
  | 'reassigned';

export interface PlanItem {
  id: string;
  title: string;
  assignedAgent?: string;
  status: PlanItemStatus;
  details?: string;
}

export interface TimelineEntry {
  timestamp: string;
  message: string;
  type?: 'info' | 'success' | 'warning' | 'error' | 'reassign';
}

export interface AgentOrchestrationEvent {
  kind: 'agent_orchestration';
  id: string;
  stage: 'thinking' | 'planning' | 'delegating' | 'working' | 'reviewing' | 'reassigning' | 'synthesizing' | 'complete';
  captainMessage: string;
  plan?: PlanItem[];
  crewmates?: CrewmateAgent[];
  timeline?: TimelineEntry[];
  activeStep?: string;
}

export type ScenarioEvent =
  | ThinkingEvent
  | MessageEvent
  | ToolCallEvent
  | ToolResultEvent
  | ToolStepEvent
  | ErrorEvent
  | WarningEvent
  | SuccessEvent
  | ProgressEvent
  | PlanReadyEvent
  | ContextCompactedEvent
  | ContextCompactionStartedEvent
  | ContextCompactionEndedEvent
  | TurnManifestEvent
  | AgentOrchestrationEvent;

export type ScenarioMode = 'plan' | 'build';

export type ContentPart =
  | { type: 'text'; text: string }
  | { type: 'reasoning'; text: string }
  | { type: 'tool_call'; id: string; name: string; params: Record<string, unknown> }
  | { type: 'tool_result'; id: string; name: string; success: boolean; output: string }
  | { type: 'finish'; reason: string };

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  parts: ContentPart[];
  timestamp: number;
}

export interface Scenario {
  id: string;
  mode: ScenarioMode;
  prompt: string;
  events: ScenarioEvent[];
  sessionId?: string;
}

export interface FileAttachment {
  path: string;
  name: string;
  mimeType: string;
  size: number;
}
