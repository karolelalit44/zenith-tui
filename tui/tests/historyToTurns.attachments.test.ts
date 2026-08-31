import { describe, expect, it } from 'vitest';
import { convertHistoryToTurns } from '../src/utils/historyToTurns';

describe('convertHistoryToTurns attachment reconstruction', () => {
  it('reconstructs attachments from persisted attachment_refs metadata', () => {
    const messages = [
      {
        id: 'm1',
        role: 'user',
        content: 'review these files',
        created_at: '2026-08-30T10:00:00Z',
        metadata: {
          mode: 'build',
          attachment_refs: [
            { path: 'src/auth/login.ts', name: 'login.ts', kind: 'file', size: 500 },
            { path: 'src/auth', name: 'auth', kind: 'folder', size: 0 },
          ],
        },
      },
    ];
    const turns = convertHistoryToTurns(messages, 'build');
    expect(turns).toHaveLength(1);
    const attachments = turns[0].attachments;
    expect(attachments).toHaveLength(2);
    expect(attachments?.[0]).toMatchObject({
      path: 'src/auth/login.ts',
      name: 'login.ts',
      kind: 'file',
      size: 500,
    });
    expect(attachments?.[1]).toMatchObject({
      path: 'src/auth',
      kind: 'folder',
      mimeType: 'inode/directory',
    });
  });

  it('leaves attachments undefined when metadata is absent', () => {
    const messages = [
      { id: 'm1', role: 'user', content: 'hi', created_at: '2026-08-30T10:00:00Z', metadata: { mode: 'plan' } },
    ];
    const turns = convertHistoryToTurns(messages, 'plan');
    expect(turns[0].attachments).toBeUndefined();
  });

  it('falls back to attachment_paths-compatible refs with only paths', () => {
    const messages = [
      {
        id: 'm1',
        role: 'user',
        content: 'x',
        created_at: '2026-08-30T10:00:00Z',
        metadata: { mode: 'build', attachment_refs: [{ path: 'a/b.ts' }] },
      },
    ];
    const turns = convertHistoryToTurns(messages, 'build');
    const attachments = turns[0].attachments;
    expect(attachments?.[0]?.name).toBe('b.ts');
    expect(attachments?.[0]?.kind).toBe('file');
  });
});
