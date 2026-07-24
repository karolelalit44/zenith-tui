import type { ScenarioEvent } from '../../types/scenario';
import type { JsonRpcEvent } from './WebSocketClient';

let idCounter = Date.now();
const uid = () => `evt_${++idCounter}`;

export function cleanMessageText(rawText: string): string {
  let cleaned = rawText;
  cleaned = cleaned.replace(/```(?:tool|json)?\s*\n?\{[\s\S]*?"tool"\s*:\s*"[^"]+"[\s\S]*?\}\s*\n?```/gi, '');
  cleaned = cleaned.replace(/\{[\s\S]*?"tool"\s*:\s*"[^"]+"[\s\S]*?"params"\s*:\s*\{[\s\S]*?\}\s*\}/gi, '');
  cleaned = cleaned.replace(/```(?:tool|json)?\s*\n?\{[\s\S]*$/gi, '');
  cleaned = cleaned.replace(/Command:\s*cd\s+.*?\nOutput:[\s\S]*?(?=\n\n|Z)/gi, '');
  cleaned = cleaned.replace(/Successfully created new file:\s*[^\n]+/gi, '');
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n');
  return cleaned.trim();
}

export function mapEvent(rpcEvent: JsonRpcEvent): ScenarioEvent {
  const { kind, data } = rpcEvent.params;

  switch (kind) {
    case 'thinking':
      return {
        kind: 'thinking',
        id: uid(),
        thoughts: data.text ? [{ text: String(data.text), delay: 50 }] : [],
        duration: typeof data.duration === 'number' ? data.duration : 500,
      } as ScenarioEvent;

    case 'message': {
      const isPartial = data.partial === true;
      const raw = String(data.text || '');
      const cleanedText = cleanMessageText(raw);
      return {
        kind: 'message',
        id: uid(),
        text: cleanedText || (isPartial ? raw : ''),
        partial: isPartial,
      } as ScenarioEvent;
    }

    case 'file_create': {
      const path = String(data.path || data.filepath || '').replace(/\\/g, '/');
      const parts = path.split('/');
      const fileName = parts.pop() || path;
      const directory = parts.join('/') || '/';
      const content = String(data.content || '');
      const lines = content ? content.split('\n').map((line) => ({ text: line, type: 'add' as const })) : [];
      return {
        kind: 'file_create',
        id: uid(),
        filePath: path,
        directory,
        lines,
        language: String(data.language || detectLanguage(fileName)),
      } as ScenarioEvent;
    }

    case 'file_edit': {
      const path = String(data.path || data.filepath || '').replace(/\\/g, '/');
      const parts = path.split('/');
      const fileName = parts.pop() || path;
      const directory = parts.join('/') || '/';
      const oldStr = String(data.old_string || '');
      const newStr = String(data.new_string || '');
      const removedLines = oldStr ? oldStr.split('\n').map((line) => ({ text: line, type: 'remove' as const })) : [];
      const addedLines = newStr ? newStr.split('\n').map((line) => ({ text: line, type: 'add' as const })) : [];
      return {
        kind: 'file_edit',
        id: uid(),
        filePath: path,
        directory,
        removedLines,
        addedLines,
        language: String(data.language || detectLanguage(fileName)),
      } as ScenarioEvent;
    }

    case 'file_delete': {
      const path = String(data.path || '');
      const parts = path.split('/');
      const fileName = parts.pop() || path;
      const directory = parts.join('/') || '/';
      return {
        kind: 'file_delete',
        id: uid(),
        filePath: path,
        directory,
        lines: [],
        language: String(data.language || detectLanguage(fileName)),
      } as ScenarioEvent;
    }

    case 'terminal':
      return {
        kind: 'terminal',
        id: uid(),
        command: String(data.command || ''),
        output: Array.isArray(data.output) ? data.output.map(String) : [],
        duration: typeof data.duration === 'number' ? data.duration : 1000,
      } as ScenarioEvent;

    case 'error':
      return {
        kind: 'error',
        id: uid(),
        message: String(data.message || 'An error occurred'),
        code: data.code ? String(data.code) : undefined,
        recoverable: typeof data.recoverable === 'boolean' ? data.recoverable : undefined,
        provider: data.provider ? String(data.provider) : undefined,
      } as ScenarioEvent;

    case 'warning':
      return {
        kind: 'warning',
        id: uid(),
        message: String(data.message || ''),
        code: data.code ? String(data.code) : undefined,
      } as ScenarioEvent;

    case 'retry':
      return {
        kind: 'retry',
        id: uid(),
        message: String(data.message || 'Retrying...'),
        attempt: typeof data.attempt === 'number' ? data.attempt : 1,
      } as ScenarioEvent;

    case 'success':
      return {
        kind: 'success',
        id: uid(),
        message: String(data.message || data.tool || 'Completed'),
        filesCreated: Array.isArray(data.filesCreated) ? data.filesCreated.map(String) : [],
        commandsExecuted: Array.isArray(data.commandsExecuted) ? data.commandsExecuted.map(String) : [],
        iterations: typeof data.iterations === 'number' ? data.iterations : undefined,
        tokenInfo:
          data.tokenInfo && typeof data.tokenInfo === 'object'
            ? {
                used: Number((data.tokenInfo as Record<string, unknown>).used) || 0,
                remaining: Number((data.tokenInfo as Record<string, unknown>).remaining) || 0,
                total: Number((data.tokenInfo as Record<string, unknown>).total) || 0,
                percent: Number((data.tokenInfo as Record<string, unknown>).percent) || 0,
              }
            : undefined,
        tool: data.tool ? String(data.tool) : undefined,
        result:
          data.result && typeof data.result === 'object'
            ? {
                success: Boolean((data.result as Record<string, unknown>).success),
                output: String((data.result as Record<string, unknown>).output || ''),
                error: String((data.result as Record<string, unknown>).error || ''),
              }
            : undefined,
      } as ScenarioEvent;

    case 'summary':
      return {
        kind: 'summary',
        id: uid(),
        title: String(data.title || data.action || 'Summary'),
        description: String(data.description || data.text || ''),
        filesCreated: Array.isArray(data.filesCreated) ? data.filesCreated.map(String) : [],
        commandsExecuted: Array.isArray(data.commandsExecuted) ? data.commandsExecuted.map(String) : [],
        verified: Array.isArray(data.verified) ? data.verified.map(String) : undefined,
        action: data.action ? String(data.action) : undefined,
      } as ScenarioEvent;

    case 'progress':
      return {
        kind: 'progress',
        id: uid(),
        label: String(data.label || data.status || 'Progress'),
        percent: typeof data.percent === 'number' ? data.percent : undefined,
        iteration: typeof data.iteration === 'number' ? data.iteration : undefined,
        steps: Array.isArray(data.steps)
          ? (data.steps as ScenarioEvent['kind' extends 'progress' ? never : never])
          : [],
      } as ScenarioEvent;

    case 'waiting':
      return {
        kind: 'waiting',
        id: uid(),
        message: String(data.message || ''),
        duration: typeof data.duration === 'number' ? data.duration : 2000,
      } as ScenarioEvent;

    case 'test_execution':
      return {
        kind: 'test_execution',
        id: uid(),
        command: String(data.command || ''),
        framework: String(data.framework || 'unknown'),
        results: Array.isArray(data.results) ? data.results : [],
        summary: (data.summary as { total: number; passed: number; failed: number; skipped: number }) || {
          total: 0,
          passed: 0,
          failed: 0,
          skipped: 0,
        },
      } as ScenarioEvent;

    case 'build_step':
      return {
        kind: 'build_step',
        id: uid(),
        step: String(data.step || ''),
        status: (data.status as 'running' | 'success' | 'error' | 'skipped') || 'running',
        output: Array.isArray(data.output) ? data.output.map(String) : undefined,
        duration: typeof data.duration === 'number' ? data.duration : undefined,
      } as ScenarioEvent;

    case 'deployment':
      return {
        kind: 'deployment',
        id: uid(),
        target: String(data.target || ''),
        status: (data.status as 'deploying' | 'success' | 'failed') || 'deploying',
        url: data.url ? String(data.url) : undefined,
        output: Array.isArray(data.output) ? data.output.map(String) : undefined,
      } as ScenarioEvent;

    case 'analysis': {
      const toolName = data.tool ? String(data.tool) : '';
      const params = (data.params || {}) as Record<string, unknown>;
      let sections: Array<{ title: string; items: string[] }> = [];

      if (Array.isArray(data.sections)) {
        sections = data.sections as Array<{ title: string; items: string[] }>;
      } else if (toolName) {
        const items: string[] = [];
        const filePath = String(params.filepath || params.path || params.file_path || '');
        const command = String(params.command || '');
        const desc = String(params.description || '');

        if (filePath) items.push(`File: ${filePath}`);
        if (command) items.push(`Command: ${command}`);
        if (desc) items.push(`Description: ${desc}`);

        if (items.length === 0) {
          items.push(`Executing ${toolName}`);
        }

        sections = [{ title: `Tool: ${toolName}`, items }];
      }

      return {
        kind: 'analysis',
        id: uid(),
        title: String(data.title || data.text || (toolName ? `Executing ${toolName}...` : 'Analysis')),
        sections,
      } as ScenarioEvent;
    }

    case 'planner_action_panel':
      return {
        kind: 'planner_action_panel',
        id: uid(),
        defaultFilename: String(data.defaultFilename || 'plan.md'),
        saved: data.saved === true,
      } as ScenarioEvent;

    case 'mode_mismatch':
      return {
        kind: 'mode_mismatch',
        id: uid(),
        currentMode: (data.currentMode as 'plan' | 'build') || 'plan',
        suggestedMode: (data.suggestedMode as 'plan' | 'build') || 'build',
        reason: String(data.reason || ''),
        prompt: String(data.prompt || ''),
      } as ScenarioEvent;

    default:
      return {
        kind: 'message',
        id: uid(),
        text: `[${kind}] ${JSON.stringify(data)}`,
      } as ScenarioEvent;
  }
}

function detectLanguage(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const langMap: Record<string, string> = {
    ts: 'typescript',
    tsx: 'typescript',
    js: 'javascript',
    jsx: 'javascript',
    py: 'python',
    rs: 'rust',
    go: 'go',
    java: 'java',
    kt: 'kotlin',
    swift: 'swift',
    rb: 'ruby',
    php: 'php',
    c: 'c',
    cpp: 'cpp',
    h: 'c',
    html: 'html',
    css: 'css',
    scss: 'scss',
    json: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    toml: 'toml',
    md: 'markdown',
    sql: 'sql',
    sh: 'bash',
    bash: 'bash',
    zsh: 'bash',
    dockerfile: 'dockerfile',
    tf: 'terraform',
  };
  return langMap[ext] || 'text';
}
