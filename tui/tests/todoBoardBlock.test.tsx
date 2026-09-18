import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { TodoBoardBlock } from '../src/components/Display/Scenario/TodoBoardBlock';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { TodoItem, TodoStatus } from '../src/types/scenario';
import { consolidateTodoBoardEvents, type ConsolidatedTodoBoard } from '../src/utils/todoBoard';

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
  it('renders the todo table rows without a column header', () => {
    const frame = frameFor(boardEvent([item('T1', 'Add CI pipeline to the repo', 'done')]));
    expect(frame).toContain('TODO');
    expect(frame).not.toContain('TODO TITLE');
    expect(frame).not.toContain('STATUS');
    expect(frame).toMatch(/T1\s+Add CI pipeline to the repo\s+success/);
  });

  it('labels done as success and blocked/cancelled as failure', () => {
    const frame = frameFor(
      boardEvent([
        item('T1', 'Done task', 'done'),
        item('T2', 'Cancelled task', 'cancelled'),
        item('T3', 'Blocked task', 'blocked'),
      ]),
    );
    expect(frame).toMatch(/T1\s+Done task\s+success/);
    expect(frame).toMatch(/T2\s+Cancelled task\s+failure/);
    expect(frame).toMatch(/T3\s+Blocked task\s+failure/);
  });

  it('labels in-progress and open items distinctly', () => {
    const frame = frameFor(boardEvent([item('T1', 'Running task', 'in_progress'), item('T2', 'Open task', 'todo')]));
    expect(frame).toMatch(/T1\s+Running task\s+in progress/);
    expect(frame).toMatch(/T2\s+Open task\s+todo/);
  });

  it('shows top-level todos only, not subtasks', () => {
    const withSubtasks = item('T1', 'Parent task', 'todo');
    withSubtasks.subtasks = [
      { id: 'T1-S1', title: 'Hidden subtask', status: 'todo' },
      { id: 'T1-S2', title: 'Another hidden subtask', status: 'done' },
    ];
    const frame = frameFor(boardEvent([withSubtasks]));
    expect(frame).toMatch(/T1\s+Parent task\s+todo/);
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
    expect(frame).toMatch(/T1\s+Build the HRMS/);
    expect(frame).toContain('success');
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
});
