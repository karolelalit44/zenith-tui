export type EventKind =
  | 'thinking'
  | 'message'
  | 'tool_call'
  | 'tool_result'
  | 'error'
  | 'warning'
  | 'success'
  | 'progress'
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
}

export interface MessageEvent {
  kind: 'message';
  id: string;
  text: string;
  partial?: boolean;
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

export interface ProgressEvent {
  kind: 'progress';
  id: string;
  label: string;
  steps: { label: string; status: 'pending' | 'active' | 'done' | 'error' }[];
  percent?: number;
  iteration?: number;
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
  | MessageEvent
  | ToolCallEvent
  | ToolResultEvent
  | ErrorEvent
  | WarningEvent
  | SuccessEvent
  | ProgressEvent
  | ConfirmationRequestEvent;

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
