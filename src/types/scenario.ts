export type EventKind =
  | 'thinking'
  | 'file_create'
  | 'file_edit'
  | 'file_delete'
  | 'terminal'
  | 'error'
  | 'warning'
  | 'retry'
  | 'success'
  | 'summary'
  | 'message'
  | 'progress'
  | 'waiting'
  | 'test_execution'
  | 'build_step'
  | 'deployment'
  | 'analysis'
  | 'planner_action_panel'
  | 'mode_mismatch'
  | 'confirmation_request';

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

export interface FileCreateEvent {
  kind: 'file_create';
  id: string;
  filePath: string;
  directory: string;
  lines: FileLine[];
  language: string;
}

export interface FileEditEvent {
  kind: 'file_edit';
  id: string;
  filePath: string;
  directory: string;
  removedLines: FileLine[];
  addedLines: FileLine[];
  language: string;
}

export interface FileDeleteEvent {
  kind: 'file_delete';
  id: string;
  filePath: string;
  directory: string;
  lines: FileLine[];
  language: string;
}

export interface TerminalEvent {
  kind: 'terminal';
  id: string;
  command: string;
  output: string[];
  duration: number;
  exitCode?: number;
}

export interface ErrorEvent {
  kind: 'error';
  id: string;
  message: string;
  code?: string;
  recoverable?: boolean;
  provider?: string;
}

export interface WarningEvent {
  kind: 'warning';
  id: string;
  message: string;
  code?: string;
}

export interface RetryEvent {
  kind: 'retry';
  id: string;
  message: string;
  attempt: number;
}

export interface ToolResultData {
  success: boolean;
  output: string;
  error: string;
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
  filesCreated: string[];
  commandsExecuted: string[];
  iterations?: number;
  tokenInfo?: TokenInfo;
  tool?: string;
  result?: ToolResultData;
}

export interface SummaryEvent {
  kind: 'summary';
  id: string;
  title: string;
  description: string;
  filesCreated: string[];
  commandsExecuted: string[];
  verified?: string[];
  action?: string;
}

export interface MessageEvent {
  kind: 'message';
  id: string;
  text: string;
  partial?: boolean;
}

export interface ProgressEvent {
  kind: 'progress';
  id: string;
  label: string;
  steps: { label: string; status: 'pending' | 'active' | 'done' | 'error' }[];
  percent?: number;
  iteration?: number;
}

export interface WaitingEvent {
  kind: 'waiting';
  id: string;
  message: string;
  duration: number;
}

export interface TestResult {
  name: string;
  status: 'pass' | 'fail' | 'skip';
  duration?: number;
  error?: string;
}

export interface TestExecutionEvent {
  kind: 'test_execution';
  id: string;
  command: string;
  framework: string;
  results: TestResult[];
  summary: { total: number; passed: number; failed: number; skipped: number };
}

export interface BuildStepEvent {
  kind: 'build_step';
  id: string;
  step: string;
  status: 'running' | 'success' | 'error' | 'skipped';
  output?: string[];
  duration?: number;
}

export interface DeploymentEvent {
  kind: 'deployment';
  id: string;
  target: string;
  status: 'deploying' | 'success' | 'failed';
  url?: string;
  output?: string[];
}

export interface AnalysisSection {
  title: string;
  items: string[];
}

export interface AnalysisEvent {
  kind: 'analysis';
  id: string;
  title: string;
  sections: AnalysisSection[];
}

export interface PlannerActionPanelEvent {
  kind: 'planner_action_panel';
  id: string;
  defaultFilename: string;
  saved?: boolean;
}

export interface ModeMismatchEvent {
  kind: 'mode_mismatch';
  id: string;
  currentMode: 'plan' | 'build';
  suggestedMode: 'plan' | 'build';
  reason: string;
  prompt: string;
}

export interface ConfirmationRequestEvent {
  kind: 'confirmation_request';
  id: string;
  confirmationId: string;
  tool: string;
  reason: string;
  riskLevel: string;
  message: string;
  answered?: boolean;
  approved?: boolean;
}

export type ScenarioEvent =
  | ThinkingEvent
  | FileCreateEvent
  | FileEditEvent
  | FileDeleteEvent
  | TerminalEvent
  | ErrorEvent
  | WarningEvent
  | RetryEvent
  | SuccessEvent
  | SummaryEvent
  | MessageEvent
  | ProgressEvent
  | WaitingEvent
  | TestExecutionEvent
  | BuildStepEvent
  | DeploymentEvent
  | AnalysisEvent
  | PlannerActionPanelEvent
  | ModeMismatchEvent
  | ConfirmationRequestEvent;

export type ScenarioMode = 'plan' | 'build';

export interface Scenario {
  id: string;
  mode: ScenarioMode;
  prompt: string;
  events: ScenarioEvent[];
}
