import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { envStr } from '../../config/env';
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

export const TODO_LIFECYCLE_FILE = 'todo-lifecycle.json';

/** Output directory for simulation artifacts (from tui/.env). */
export function simOutputDir(): string {
  return path.resolve(envStr('ZENITH_SIM_OUTPUT_DIR'));
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
