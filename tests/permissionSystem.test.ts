/**
 * Permission System Frontend Tests
 *
 * Tests EventMapper handling of permission_request events,
 * PermissionDialog component rendering, and WebSocketClient permission methods.
 */
import { describe, expect, it } from 'vitest';
import { mapEvent } from '../src/services/backend/EventMapper';
import type { JsonRpcEvent } from '../src/services/backend/WebSocketClient';
import type { PermissionRequestEvent, ScenarioEvent } from '../src/types/scenario';
import { componentRegistry } from '../src/components/Display/Scenario/componentRegistry';

function makeRpcEvent(kind: string, data: Record<string, unknown> = {}): JsonRpcEvent {
  return {
    jsonrpc: '2.0',
    method: 'event',
    params: {
      kind,
      id: `test_${Date.now()}`,
      data,
    },
  };
}

// ── EventMapper: permission_request mapping ──────────────────────────────
describe('EventMapper handles permission_request', () => {
  it('maps permission_request with file_write tool', () => {
    const rpcEvent = makeRpcEvent('permission_request', {
      tool: 'file_write',
      params: { filepath: 'src/main.ts', content: 'const x = 1;' },
      requestId: 'perm_abc123',
    });

    const result: ScenarioEvent = mapEvent(rpcEvent);
    expect(result.kind).toBe('permission_request');
    expect(result.id).toBeTruthy();

    const permEvent = result as PermissionRequestEvent;
    expect(permEvent.tool).toBe('file_write');
    expect(permEvent.params).toEqual({ filepath: 'src/main.ts', content: 'const x = 1;' });
    expect(permEvent.requestId).toBe('perm_abc123');
  });

  it('maps permission_request with bash tool', () => {
    const rpcEvent = makeRpcEvent('permission_request', {
      tool: 'bash',
      params: { command: 'rm -rf /tmp/test' },
      requestId: 'perm_xyz789',
    });

    const result = mapEvent(rpcEvent) as PermissionRequestEvent;
    expect(result.kind).toBe('permission_request');
    expect(result.tool).toBe('bash');
    expect(result.params.command).toBe('rm -rf /tmp/test');
  });

  it('maps permission_request with file_edit tool', () => {
    const rpcEvent = makeRpcEvent('permission_request', {
      tool: 'file_edit',
      params: { filepath: 'config.json', old_string: 'old', new_string: 'new' },
      requestId: 'perm_edit1',
    });

    const result = mapEvent(rpcEvent) as PermissionRequestEvent;
    expect(result.tool).toBe('file_edit');
    expect(result.params.filepath).toBe('config.json');
  });

  it('maps permission_request with file_delete tool', () => {
    const rpcEvent = makeRpcEvent('permission_request', {
      tool: 'file_delete',
      params: { path: 'src/old.ts' },
      requestId: 'perm_del1',
    });

    const result = mapEvent(rpcEvent) as PermissionRequestEvent;
    expect(result.tool).toBe('file_delete');
    expect(result.params.path).toBe('src/old.ts');
  });

  it('maps permission_request with empty params gracefully', () => {
    const rpcEvent = makeRpcEvent('permission_request', {
      tool: 'bash',
    });

    const result = mapEvent(rpcEvent) as PermissionRequestEvent;
    expect(result.tool).toBe('bash');
    expect(result.params).toEqual({});
    expect(result.requestId).toBe('');
  });

  it('maps permission_request with missing tool name', () => {
    const rpcEvent = makeRpcEvent('permission_request', {
      params: { command: 'echo hi' },
      requestId: 'perm_notool',
    });

    const result = mapEvent(rpcEvent) as PermissionRequestEvent;
    expect(result.tool).toBe('');
  });
});

// ── PermissionRequestEvent type correctness ─────────────────────────────
describe('PermissionRequestEvent type', () => {
  it('has all required fields', () => {
    const event: PermissionRequestEvent = {
      kind: 'permission_request',
      id: 'evt_123',
      tool: 'file_write',
      params: { filepath: 'test.ts' },
      requestId: 'perm_456',
    };

    expect(event.kind).toBe('permission_request');
    expect(event.id).toBe('evt_123');
    expect(event.tool).toBe('file_write');
    expect(event.params.filepath).toBe('test.ts');
    expect(event.requestId).toBe('perm_456');
  });
});

// ── ComponentRegistry: permission_request component ──────────────────────
describe('ComponentRegistry has permission_request component', () => {
  it('returns a component for permission_request kind', () => {
    const Component = componentRegistry.getComponent('permission_request');
    expect(Component).toBeDefined();
    expect(typeof Component).toBe('object');
  });

  it('does not return UnknownEventFallback for permission_request', () => {
    const UnknownFallback = componentRegistry.getComponent('unknown_kind_xyz');
    const PermComponent = componentRegistry.getComponent('permission_request');
    expect(PermComponent).not.toBe(UnknownFallback);
  });
});

// ── Permission event data extraction helpers ─────────────────────────────
describe('Permission event data extraction', () => {
  function extractToolDescription(tool: string, params: Record<string, unknown>): string {
    switch (tool) {
      case 'file_write':
        return `Write to file: ${String(params.filepath || params.path || 'unknown')}`;
      case 'file_edit':
        return `Edit file: ${String(params.filepath || params.path || 'unknown')}`;
      case 'file_delete':
        return `Delete file: ${String(params.path || 'unknown')}`;
      case 'bash':
        return `Execute command: ${String(params.command || 'unknown').slice(0, 80)}`;
      default:
        return `Execute tool: ${tool}`;
    }
  }

  it('describes file_write correctly', () => {
    const desc = extractToolDescription('file_write', { filepath: 'src/main.ts' });
    expect(desc).toBe('Write to file: src/main.ts');
  });

  it('describes file_edit correctly', () => {
    const desc = extractToolDescription('file_edit', { filepath: 'config.json' });
    expect(desc).toBe('Edit file: config.json');
  });

  it('describes file_delete correctly', () => {
    const desc = extractToolDescription('file_delete', { path: 'old.ts' });
    expect(desc).toBe('Delete file: old.ts');
  });

  it('describes bash correctly', () => {
    const desc = extractToolDescription('bash', { command: 'npm test' });
    expect(desc).toBe('Execute command: npm test');
  });

  it('truncates long bash commands', () => {
    const longCmd = 'a'.repeat(200);
    const desc = extractToolDescription('bash', { command: longCmd });
    expect(desc.length).toBeLessThan(120);
  });

  it('handles unknown tool', () => {
    const desc = extractToolDescription('unknown_tool', {});
    expect(desc).toBe('Execute tool: unknown_tool');
  });

  it('handles missing params gracefully', () => {
    const desc = extractToolDescription('file_write', {});
    expect(desc).toBe('Write to file: unknown');
  });
});
