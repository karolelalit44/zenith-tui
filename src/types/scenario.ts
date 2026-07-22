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
  | 'planner_action_panel';

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
}

export interface ErrorEvent {
  kind: 'error';
  id: string;
  message: string;
  command?: string;
  stack?: string;
}

export interface WarningEvent {
  kind: 'warning';
  id: string;
  message: string;
  details?: string;
}

export interface RetryEvent {
  kind: 'retry';
  id: string;
  message: string;
  attempt: number;
}

export interface SuccessEvent {
  kind: 'success';
  id: string;
  message: string;
  filesCreated: string[];
  commandsExecuted: string[];
}

export interface SummaryEvent {
  kind: 'summary';
  id: string;
  title: string;
  description: string;
  filesCreated: string[];
  commandsExecuted: string[];
  verified?: string[];
}

export interface MessageEvent {
  kind: 'message';
  id: string;
  text: string;
}

export interface ProgressEvent {
  kind: 'progress';
  id: string;
  label: string;
  steps: { label: string; status: 'pending' | 'active' | 'done' | 'error' }[];
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
  | PlannerActionPanelEvent;

export type ScenarioMode = 'plan' | 'build';

export interface Scenario {
  id: string;
  mode: ScenarioMode;
  prompt: string;
  events: ScenarioEvent[];
}
