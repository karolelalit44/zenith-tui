import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { TodoBoardBlock } from '../src/components/Display/Scenario/TodoBoardBlock';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { TodoItem, TodoStatus } from '../src/types/scenario';
import { type ConsolidatedTodoBoard, consolidateTodoBoardEvents } from '../src/utils/todoBoard';

const item = (id: string, title: string, status: TodoStatus): TodoItem => ({
  id,
  title,
  status,
  priority: 'medium',
  createdAt: 0,
  updatedAt: 0,
  subtasks: [],
});

const boardEvent = (board: TodoItem[]): ConsolidatedTodoBoard => ({
  kind: 'todo_board',
  id: 'tb_1',
  action: 'snapshot',
  board,
  activity: [],
});

function frameFor(event: ConsolidatedTodoBoard, columns?: number): string {
  const original = Object.getOwnPropertyDescriptor(process.stdout, 'columns');
  if (columns !== undefined) {
    Object.defineProperty(process.stdout, 'columns', { configurable: true, get: () => columns });
  }
  try {
    const { lastFrame } = render(
      <ThemeProvider>
        <TodoBoardBlock event={event} />
      </ThemeProvider>,
    );
    return lastFrame();
  } finally {
    if (original) Object.defineProperty(process.stdout, 'columns', original);
    else delete (process.stdout as { columns?: number }).columns;
  }
}

describe('TodoBoardBlock', () => {
  it('renders strict three columns: serial | title | status symbol only', () => {
    const frame = frameFor(boardEvent([item('T1', 'Add CI pipeline to the repo', 'done')]));
    expect(frame).toContain('TODO');
    expect(frame).not.toContain('TODO TITLE');
    expect(frame).not.toContain('STATUS');
    expect(frame).toMatch(/1\s+Add CI pipeline to the repo\s+✔/);
    // Serial is positional (1), never the backend id; status is symbol-only.
    expect(frame).not.toContain('T1');
    expect(frame).not.toContain('success');
  });

  it('maps every status to its symbol only', () => {
    const frame = frameFor(
      boardEvent([
        item('T1', 'Done task', 'done'),
        item('T2', 'Cancelled task', 'cancelled'),
        item('T3', 'Blocked task', 'blocked'),
      ]),
    );
    expect(frame).toMatch(/1\s+Done task\s+✔/);
    expect(frame).toMatch(/2\s+Cancelled task\s+✖/);
    expect(frame).toMatch(/3\s+Blocked task\s+✖/);
    expect(frame).not.toContain('success');
    expect(frame).not.toContain('failure');
  });

  it('labels in-progress and open items with symbols only', () => {
    const frame = frameFor(boardEvent([item('T1', 'Running task', 'in_progress'), item('T2', 'Open task', 'todo')]));
    expect(frame).toMatch(/1\s+Running task\s+◐/);
    expect(frame).toMatch(/2\s+Open task\s+○/);
    expect(frame).not.toContain('in progress');
  });

  it('shows top-level todos only, not subtasks', () => {
    const withSubtasks = item('T1', 'Parent task', 'todo');
    withSubtasks.subtasks = [
      { id: 'T1-S1', title: 'Hidden subtask', status: 'todo' },
      { id: 'T1-S2', title: 'Another hidden subtask', status: 'done' },
    ];
    const frame = frameFor(boardEvent([withSubtasks]));
    expect(frame).toMatch(/1\s+Parent task\s+○/);
    expect(frame).not.toContain('Hidden subtask');
    expect(frame).not.toContain('T1-S1');
  });

  it('caps the list at 10 rows and reports the remainder', () => {
    const board = Array.from({ length: 13 }, (_, i) => item(`T${i + 1}`, `Task ${i + 1}`, 'todo'));
    const frame = frameFor(boardEvent(board));
    for (let i = 1; i <= 10; i++) {
      expect(frame).toContain(`Task ${i}`);
    }
    expect(frame).not.toContain('Task 11');
    expect(frame).toContain('+3 more…');
  });

  it('truncates long titles to the terminal width', () => {
    const longTitle = 'Build the HRMS employee onboarding module with a payroll engine and leave management';
    const frame = frameFor(boardEvent([item('T1', longTitle, 'done')]), 40);
    expect(frame).toContain('…');
    expect(frame).not.toContain(longTitle);
    expect(frame).toMatch(/1\s+Build the HRMS/);
    expect(frame).toContain('✔');
  });

  it('shows an empty state when the board has no items', () => {
    expect(frameFor(boardEvent([]))).toContain('(no todos yet)');
  });

  it('never renders the underlying assertion report', () => {
    const frame = frameFor(boardEvent([item('T1', 'Done task', 'done')]));
    expect(frame).not.toContain(' ALL SCENARIOS PASSED');
    expect(frame).not.toContain('assertions');
    expect(frame).not.toContain('REJECTED EDGE CASES');
  });

  it('consolidateTodoBoardEvents extracts board from tool_step when todo_board event is absent', () => {
    const toolStepEv = {
      kind: 'tool_step' as const,
      id: 'ts_1',
      tool: 'todo',
      params: { action: 'write' },
      success: true,
      output: 'Task board updated',
      error: '',
      pending: false,
      metadata: {
        board: [item('t1', 'Step task', 'in_progress')],
        action: 'write',
      },
    };
    const res = consolidateTodoBoardEvents([toolStepEv as any]);
    expect(res).not.toBeNull();
    expect(res?.board[0].title).toBe('Step task');
    expect(res?.board[0].status).toBe('in_progress');
  });

  it('consolidateTodoBoardEvents extracts board preview from tool_call when in-flight', () => {
    const toolCallEv = {
      kind: 'tool_call' as const,
      id: 'tc_1',
      tool: 'todo',
      params: {
        action: 'write',
        tasks: [{ id: 't1', title: 'In-flight task', status: 'in_progress' }],
      },
    };
    const res = consolidateTodoBoardEvents([toolCallEv as any]);
    expect(res).not.toBeNull();
    expect(res?.board[0].title).toBe('In-flight task');
    expect(res?.board[0].status).toBe('in_progress');
  });

  it('does not resurrect removed tasks from earlier todo_board snapshots (zombie task prevention)', () => {
    const ev1: ConsolidatedTodoBoard = {
      kind: 'todo_board',
      id: 'tb_1',
      action: 'snapshot',
      board: [item('t1', 'Task to remove', 'todo'), item('t2', 'Keep this', 'in_progress')],
      activity: [],
    };
    const ev2: ConsolidatedTodoBoard = {
      kind: 'todo_board',
      id: 'tb_2',
      action: 'snapshot',
      board: [item('t2', 'Keep this', 'in_progress')],
      activity: [],
    };
    const res = consolidateTodoBoardEvents([ev1 as any, ev2 as any]);
    expect(res).not.toBeNull();
    expect(res?.board.length).toBe(1);
    expect(res?.board[0].id).toBe('t2');
    expect(res?.board.find((t) => t.id === 't1')).toBeUndefined();
  });

  it('extracts in-flight tool_call preview even when prior todo_board snapshots exist', () => {
    const ev1: ConsolidatedTodoBoard = {
      kind: 'todo_board',
      id: 'tb_1',
      action: 'snapshot',
      board: [item('t1', 'Step 1', 'done')],
      activity: [],
    };
    const toolCallEv = {
      kind: 'tool_call' as const,
      id: 'tc_2',
      tool: 'todo',
      params: {
        action: 'write',
        tasks: [
          { id: 't1', title: 'Step 1', status: 'done' },
          { id: 't2', title: 'Step 2', status: 'in_progress' },
        ],
      },
    };
    const res = consolidateTodoBoardEvents([ev1 as any, toolCallEv as any]);
    expect(res).not.toBeNull();
    expect(res?.board.length).toBe(2);
    expect(res?.board[1].title).toBe('Step 2');
    expect(res?.board[1].status).toBe('in_progress');
  });
});
