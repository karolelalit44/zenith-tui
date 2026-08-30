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
  | 'context_compaction_phase'
  | 'context_compaction_flow'
  | 'captain_orchestration'
  | 'crewmate_spawned'
  | 'crewmate_status'
  | 'crewmate_complete'
  | 'crewmate_failed'
  | 'todo_board'
  | 'todo_test'
  | 'session_created'
  | 'session_resumed'
  | 'session_state_changed'
  | 'session_paused'
  | 'session_renamed'
  | 'session_error'
  | 'session_status'
  | 'session_summarized'
  | 'context_updated'
  | 'token_usage_recorded';

export interface ThinkingThought {
  text: string;
  delay?: number;
}

export interface ThinkingEvent {
  kind: 'thinking';
  id: string;
  thoughts: string[] | ThinkingThought[];
  duration: number;
  /** Streaming placeholder — replaced in place by the next partial/final. */
  partial?: boolean;
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
  /** Context occupancy (composed messages) — drives the context gauge. */
  used: number;
  remaining: number;
  total: number;
  percent: number;
  /** True when usage is estimated from characters, not reported by the provider. */
  estimated?: boolean;
  /** True when the model's context window is unknown and a fallback was used. */
  windowEstimated?: boolean;
  /** Cumulative run/API usage (telemetry only — never used as context occupancy). */
  runTotal?: number;
  runPrompt?: number;
  runCompletion?: number;
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

export type CompactionTrigger = 'automatic' | 'manual';
export type CompactionStatus =
  | 'started'
  | 'preserving'
  | 'compacting'
  | 'verifying'
  | 'completed'
  | 'failed'
  | 'skipped';

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
  /** Who initiated the compaction: `automatic` (threshold) or `manual` (RPC). */
  trigger?: CompactionTrigger;
  status?: CompactionStatus;
}

export interface ContextCompactionEndedEvent {
  kind: 'context_compaction_ended';
  id: string;
  message: string;
  tokensSaved?: number;
  summaryChars?: number;
  used?: number;
  total?: number;
  preserved?: ContextPreservation;
  failed?: boolean;
  /** Human-readable summary of what the compaction pass preserved. */
  summary?: string;
  /** Who initiated the compaction: `automatic` (threshold) or `manual` (RPC). */
  trigger?: CompactionTrigger;
  status?: CompactionStatus;
}

/**
 * Explicit phase transition emitted by the compaction pipeline so the UI can
 * animate the full compaction lifecycle dynamically. The backend emits one of
 * these for each stage (preserving → compacting → verifying).
 */
export interface ContextCompactionPhaseEvent {
  kind: 'context_compaction_phase';
  id: string;
  phase: CompactionPhase;
  label?: string;
  beforeTokens?: number;
  afterTokens?: number;
  /** Who initiated the compaction: `automatic` (threshold) or `manual` (RPC). */
  trigger?: CompactionTrigger;
}

export type CompactionPhase = 'preparing' | 'preserving' | 'compacting' | 'verifying' | 'ready' | 'failed';

/**
 * Structured record of what a compaction pass preserved or compressed.
 * Every field is optional: the UI must never fabricate metrics the backend
 * did not actually calculate.
 */
export interface ContextPreservation {
  requirements?: number;
  decisions?: number;
  openTasks?: number;
  findings?: number;
  artifacts?: number;
  agents?: number;
  compressedDiscussions?: number;
  redundantExchanges?: number;
  obsoleteStates?: number;
}

/**
 * Synthetic, consolidated compaction lifecycle event. The ScenarioRenderer
 * folds `context_compaction_started` / `context_compacted` /
 * `context_compaction_ended` into a single one of these so the UI renders ONE
 * continuous status component instead of many duplicate rows.
 */
export interface ContextCompactionFlowEvent {
  kind: 'context_compaction_flow';
  id: string;
  phase: CompactionPhase;
  beforeTokens?: number;
  afterTokens?: number;
  totalTokens?: number;
  tokensSaved?: number;
  summaryChars?: number;
  preserved?: ContextPreservation;
  /** Short sub-lines captured from tool-level compaction steps (max ~3). */
  notes?: string[];
  /** Human-readable summary of what the compaction pass preserved. */
  summary?: string;
  failed?: boolean;
  /** Who initiated the compaction: `automatic` (threshold) or `manual` (RPC). */
  trigger?: CompactionTrigger;
  status?: CompactionStatus;
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

export type PlanItemStatus = 'queued' | 'in_progress' | 'completed' | 'needs_review' | 'failed' | 'reassigned';

export interface PlanItem {
  id: string;
  title: string;
  assignedCrewmate?: string;
  status: PlanItemStatus;
  details?: string;
}

export interface TimelineEntry {
  timestamp: string;
  message: string;
  type?: 'info' | 'success' | 'warning' | 'error' | 'reassign';
}

export interface CaptainOrchestrationEvent {
  kind: 'captain_orchestration';
  id: string;
  stage: 'thinking' | 'planning' | 'delegating' | 'working' | 'reviewing' | 'reassigning' | 'synthesizing' | 'complete';
  captainMessage: string;
  plan?: PlanItem[];
  crewmates?: CrewmateAgent[];
  timeline?: TimelineEntry[];
  activeStep?: string;
}

export interface CrewmateSpawnedEvent {
  kind: 'crewmate_spawned';
  id: string;
  crewmateId: string;
  name: string;
  role: string;
  taskId: string;
  capability: string;
  parentSessionId?: string;
  model?: string;
}

export interface CrewmateStatusEvent {
  kind: 'crewmate_status';
  id: string;
  crewmateId: string;
  status: string;
  activity?: string;
  progress?: number;
}

export interface CrewmateCompleteEvent {
  kind: 'crewmate_complete';
  id: string;
  crewmateId: string;
  taskId: string;
  resultSummary?: string;
  status?: string;
}

export interface CrewmateFailedEvent {
  kind: 'crewmate_failed';
  id: string;
  crewmateId: string;
  taskId: string;
  error?: string;
}

export type TodoStatus = 'todo' | 'in_progress' | 'blocked' | 'done' | 'cancelled';

export type TodoPriority = 'low' | 'medium' | 'high' | 'urgent';

export interface SubtaskItem {
  id: string;
  title: string;
  status: TodoStatus;
  assignee?: string;
  note?: string;
}

/**
 * A single work item on the todo board. `progress` is always derived in the UI
 * from `status` + subtasks and is never trusted from the wire.
 */
export interface TodoItem {
  id: string;
  title: string;
  status: TodoStatus;
  priority: TodoPriority;
  assignee?: string;
  labels?: string[];
  dueDate?: string;
  createdAt: number;
  updatedAt: number;
  subtasks: SubtaskItem[];
}

export type TodoBoardAction = 'created' | 'updated' | 'completed' | 'cancelled' | 'snapshot';

export interface TodoBoardChange {
  itemId: string;
  field: string;
  from?: unknown;
  to?: unknown;
}

/**
 * A snapshot of the entire todo board. Every emission carries the FULL board
 * so the UI is a pure function of the latest event — any backend that emits
 * this shape (live WS or fixture) renders identically with zero UI changes.
 */
export interface TodoBoardEvent {
  kind: 'todo_board';
  id: string;
  action: TodoBoardAction;
  board: TodoItem[];
  change?: TodoBoardChange;
  message?: string;
}

/**
 * Lifecycle phases exercised by the todo lifecycle simulation (triggered by a
 * matching prompt against the test backend's `data/simulation` playback).
 * Ordered so the report card can render a phase stepper.
 */
export type TodoLifecyclePhase = 'create' | 'manage' | 'update' | 'progress' | 'complete' | 'reopen' | 'persist';

export interface TodoTestAssertion {
  label: string;
  passed: boolean;
  detail?: string;
}

/** An invalid/incomplete-state operation that was attempted and correctly rejected. */
export interface TodoTestRejectedOp {
  op: string;
  reason: string;
}

/**
 * One scenario result from the todo lifecycle simulation. These are internal
 * test-layer events: the stream still carries them (server tests assert the
 * counts), but the ScenarioRenderer does not render them — the visible todo
 * window is the minimal board list.
 */
export interface TodoTestEvent {
  kind: 'todo_test';
  id: string;
  phase: TodoLifecyclePhase;
  scenario: string;
  passed: boolean;
  assertions: TodoTestAssertion[];
  rejectedOps?: TodoTestRejectedOp[];
  elapsedMs?: number;
}

/**
 * Lightweight session lifecycle status line (e.g. "Session created", "Session
 * resumed"). Backend session events carry a `session_id` plus a small number of
 * fields; they are operational signals, so the UI renders them as dim status
 * lines rather than prominent cards.
 */
export interface SessionInfoEvent {
  kind:
    | 'session_created'
    | 'session_resumed'
    | 'session_state_changed'
    | 'session_paused'
    | 'session_duplicated'
    | 'session_archived'
    | 'session_deleted'
    | 'session_restored'
    | 'session_renamed'
    | 'session_error'
    | 'session_status';
  id: string;
  sessionId?: string;
  /** Short human line summarizing the transition (derived from kind + fields). */
  message: string;
  fromState?: string;
  toState?: string;
  reason?: string;
  title?: string;
  error?: string;
  /** Original session id for `session_duplicated`. */
  originalId?: string;
  /** Current run status when the backend broadcasts a `session_status` row. */
  status?: string;
}

/**
 * Composed-context occupancy snapshot pushed by the backend as context grows
 * (`context_updated`). Purely informational: the authoritative frame for the
 * gauge remains the SUCCESS `tokenInfo`. Not the same as cumulative run usage.
 */
export interface ContextUpdatedEvent {
  kind: 'context_updated';
  id: string;
  sessionId?: string;
  used: number;
  total: number;
  percent: number;
}

/**
 * Provider-billed token accounting row pushed by the backend
 * (`token_usage_recorded`). Cumulative API spend only — never the composed
 * context occupancy. `totalTokens` is the provider-billed run total.
 */
export interface TokenUsageRecordedEvent {
  kind: 'token_usage_recorded';
  id: string;
  sessionId?: string;
  totalTokens: number;
  totalCost?: number;
  addedTokens?: number;
  addedCost?: number;
}

/**
 * Structured snapshot of the backend's authoritative SessionRunState. Every
 * field is optional and the UI never fabricates values the wire did not carry.
 * `final` is the terminal outcome record (kind/message/code) closed by a
 * SUCCESS or ERROR event; `manifest` is the turn manifest's created/modified
 * record; `todo` mirrors the session todo board.
 */
export interface RunStateSnapshot {
  status?: string;
  mode?: string;
  objective?: string;
  findings?: string[];
  startedAt?: number;
  updatedAt?: number;
  final?: {
    kind?: string;
    message?: string;
    code?: unknown;
  };
  manifest?: {
    created?: string[];
    modified?: string[];
    remaining?: string[];
    completed?: boolean;
    stalled?: boolean;
  };
  todo?: {
    id: string;
    title: string;
    status: TodoStatus;
    priority?: string;
  }[];
  progress?: {
    label: string;
    seq?: number;
    ts?: number;
  }[];
}

/**
 * End-of-run summary pushed by the backend (`session_summarized`). Carries the
 * authoritative SessionRunState snapshot plus an optional human summary; the
 * FinalSummaryCard renders from `runState`, never from prose.
 */
export interface SessionSummarizedEvent {
  kind: 'session_summarized';
  id: string;
  sessionId?: string;
  /** Optional human-readable summary (compact context summary, when present). */
  summary?: string;
  /** Convenience mirror of `runState.findings` (what the run discovered). */
  findings?: string[];
  runState?: RunStateSnapshot;
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
  | ContextCompactionPhaseEvent
  | ContextCompactionFlowEvent
  | TurnManifestEvent
  | CaptainOrchestrationEvent
  | CrewmateSpawnedEvent
  | CrewmateStatusEvent
  | CrewmateCompleteEvent
  | CrewmateFailedEvent
  | TodoBoardEvent
  | TodoTestEvent
  | SessionInfoEvent
  | SessionSummarizedEvent
  | ContextUpdatedEvent
  | TokenUsageRecordedEvent;

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

export type ScenarioListener = (event: ScenarioEvent, index: number) => void;

export interface ScenarioRunner {
  abort: () => void;
}

export interface ScenarioProvider {
  readonly name: string;
  resolve(prompt: string, mode: ScenarioMode): Scenario;
  execute(scenario: Scenario, onEvent: ScenarioListener, onComplete: () => void): ScenarioRunner;
}
