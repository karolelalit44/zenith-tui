import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { todoPersistence } from '../src/services/todo/todoPersistence';
import { TodoStore } from '../src/services/todo/todoStore';

let tempDir: string;

beforeEach(() => {
  tempDir = mkdtempSync(path.join(tmpdir(), 'todo-persist-'));
});

afterEach(() => {
  rmSync(tempDir, { recursive: true, force: true });
});

describe('todoPersistence', () => {
  it('saves and loads a board round-trip losslessly', () => {
    const store = new TodoStore([], { now: () => 1000 });
    store.createTodo({
      id: 'T1',
      title: 'A',
      priority: 'urgent',
      labels: ['x'],
      subtasks: [{ title: 'S1', status: 'done' }],
    });
    const board = store.snapshot();

    const filePath = path.join(tempDir, 'todo-lifecycle.json');
    todoPersistence.save(filePath, board);
    expect(() => JSON.parse(readFileSync(filePath, 'utf8'))).not.toThrow();

    const loaded = todoPersistence.load(filePath);
    expect(loaded).toEqual(board);

    const fresh = new TodoStore(loaded);
    expect(fresh.snapshot()).toEqual(board);
  });

  it('creates the parent directory automatically', () => {
    const nested = path.join(tempDir, 'deep', 'nested', 'todo-lifecycle.json');
    todoPersistence.save(nested, []);
    expect(readFileSync(nested, 'utf8')).toBe('[]');
  });

  it('rejects saving a non-array board', () => {
    expect(() => todoPersistence.save(path.join(tempDir, 'x.json'), {} as never)).toThrow(/must be an array/);
  });

  it('throws a helpful error when the file is missing or invalid', () => {
    expect(() => todoPersistence.load(path.join(tempDir, 'missing.json'))).toThrow();
    const filePath = path.join(tempDir, 'bad.json');
    todoPersistence.save(filePath, []);
    // Corrupt the file on purpose.
    writeFileSync(filePath, '{not json', 'utf8');
    expect(() => todoPersistence.load(filePath)).toThrow();
  });

  it('loads a JSON that is not an array as an invalid board', () => {
    const filePath = path.join(tempDir, 'obj.json');
    writeFileSync(filePath, '{"board": []}', 'utf8');
    expect(() => todoPersistence.load(filePath)).toThrow(/does not contain a todo board/);
  });
});
