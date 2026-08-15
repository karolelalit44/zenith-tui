import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path, { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { TodoItem } from '../../types/scenario';

/**
 * Persistence port for the todo lifecycle simulation. Kept as an injectable
 * interface so the lifecycle driver can be unit-tested against a temp directory
 * while the real TUI writes to a gitignored runtime folder.
 */
export interface BoardPersistence {
  save(filePath: string, board: TodoItem[]): void;
  load(filePath: string): TodoItem[];
}

export const TODO_BOARD_FILE = 'todo-board.json';

/**
 * Output directory for the todo board snapshot: the single canonical simulation
 * folder `data/simulation` at the repo root (same folder the server scans for
 * scripted playback). The board snapshot uses a distinct filename so it never
 * collides with the `todo-lifecycle.json` playback script.
 */
export function boardOutputDir(): string {
  return path.resolve(dirname(fileURLToPath(import.meta.url)), '../../../../data/simulation');
}

export const todoPersistence: BoardPersistence = {
  save(filePath, board) {
    if (!Array.isArray(board)) {
      throw new Error('persist rejected: board must be an array of todos');
    }
    mkdirSync(path.dirname(filePath), { recursive: true });
    writeFileSync(filePath, JSON.stringify(board, null, 2), 'utf8');
  },
  load(filePath) {
    const raw = readFileSync(filePath, 'utf8');
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      throw new Error(`reload rejected: "${filePath}" does not contain a todo board`);
    }
    return parsed as TodoItem[];
  },
};
