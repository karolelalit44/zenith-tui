import { render } from 'ink-testing-library';
import React from 'react';
import { describe, expect, it } from 'vitest';
import { PinnedTodoCard } from '../src/components/Display/Scenario/PinnedTodoCard';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { TodoItem, TodoStatus } from '../src/types/scenario';
import type { ConsolidatedTodoBoard } from '../src/utils/todoBoard';

const makeItem = (id: string, title: string, status: TodoStatus, priority?: string): TodoItem => ({
  id,
  title,
  status,
  priority: (priority as any) || 'medium',
  createdAt: 0,
  updatedAt: 0,
  subtasks: [],
});

const makeBoard = (board: TodoItem[]): ConsolidatedTodoBoard => ({
  kind: 'todo_board',
  id: 'tb_test',
  action: 'snapshot',
  board,
  activity: [],
});

function renderCard(event: ConsolidatedTodoBoard, isRunning = false) {
  const { lastFrame } = render(
    <ThemeProvider>
      <PinnedTodoCard event={event} isRunning={isRunning} />
    </ThemeProvider>,
  );
  return lastFrame();
}

describe('PinnedTodoCard', () => {
  it('renders null when board is empty', () => {
    const frame = renderCard(makeBoard([]));
    expect(frame).toBe('');
  });

  it('renders progress bar, ratio, and percentage for completed tasks', () => {
    const frame = renderCard(
      makeBoard([
        makeItem('T1', 'First task', 'done'),
        makeItem('T2', 'Second task', 'in_progress'),
        makeItem('T3', 'Third task', 'todo'),
      ]),
    );

    expect(frame).toContain('Tasks');
    expect(frame).toContain('(1/3)');
    expect(frame).toContain('33%');
    expect(frame).toContain('First task');
    expect(frame).toContain('Second task');
    expect(frame).toContain('Third task');
    // Active task title in ticker
    expect(frame).toContain('Second task');
  });

  it('renders all complete banner when 100% finished', () => {
    const frame = renderCard(
      makeBoard([
        makeItem('T1', 'Task one', 'done'),
        makeItem('T2', 'Task two', 'done'),
      ]),
    );

    expect(frame).toContain('(2/2)');
    expect(frame).toContain('100%');
    expect(frame).toContain('All complete');
  });

  it('caps visible items at 5 and displays overflow count', () => {
    const items = Array.from({ length: 8 }, (_, i) =>
      makeItem(`T${i + 1}`, `Item ${i + 1}`, i < 2 ? 'done' : 'todo'),
    );
    const frame = renderCard(makeBoard(items));

    expect(frame).toContain('(2/8)');
    expect(frame).toContain('T1');
    expect(frame).toContain('T5');
    expect(frame).not.toContain('Item 6');
    expect(frame).toContain('+3 more tasks…');
  });

  it('renders priority tag for high priority items', () => {
    const frame = renderCard(
      makeBoard([
        makeItem('T1', 'High priority item', 'todo', 'high'),
      ]),
    );

    expect(frame).toContain('[high]');
  });
});
