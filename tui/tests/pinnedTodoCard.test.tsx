import { render } from 'ink-testing-library';
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

function frameForNarrow(event: ConsolidatedTodoBoard, columns: number): string {
  const original = Object.getOwnPropertyDescriptor(process.stdout, 'columns');
  Object.defineProperty(process.stdout, 'columns', { configurable: true, get: () => columns });
  try {
    return renderCard(event);
  } finally {
    if (original) Object.defineProperty(process.stdout, 'columns', original);
    else delete (process.stdout as { columns?: number }).columns;
  }
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
    const frame = renderCard(makeBoard([makeItem('T1', 'Task one', 'done'), makeItem('T2', 'Task two', 'done')]));

    expect(frame).toContain('(2/2)');
    expect(frame).toContain('100%');
    expect(frame).toContain('All complete');
  });

  it('caps visible items at 5 and displays overflow count', () => {
    const items = Array.from({ length: 8 }, (_, i) => makeItem(`T${i + 1}`, `Item ${i + 1}`, i < 2 ? 'done' : 'todo'));
    const frame = renderCard(makeBoard(items));

    expect(frame).toContain('(2/8)');
    expect(frame).toContain('Item 1');
    expect(frame).toContain('Item 5');
    expect(frame).not.toContain('Item 6');
    expect(frame).toContain('+3 more tasks…');
    // Rows use positional serials, never backend ids.
    expect(frame).not.toContain('T1');
    expect(frame).not.toContain('T5');
  });

  it('renders positional serials regardless of backend ids', () => {
    const frame = renderCard(
      makeBoard([makeItem('XYZ-99', 'First task', 'todo'), makeItem('ABC-01', 'Second task', 'done')]),
    );

    expect(frame).toMatch(/1\s+First task\s+○/);
    expect(frame).toMatch(/2\s+Second task\s+✔/);
    expect(frame).not.toContain('XYZ-99');
    expect(frame).not.toContain('ABC-01');
  });

  it('shows status symbols only with no priority, notes, or dependency columns', () => {
    const frame = renderCard(makeBoard([makeItem('T1', 'High priority item', 'todo', 'high')]));

    expect(frame).toContain('High priority item');
    expect(frame).toContain('○');
    expect(frame).not.toContain('[high]');
    expect(frame).not.toContain('PENDING');
    expect(frame).not.toContain('└ Note:');
    expect(frame).not.toContain('└ Depends on:');
  });

  it('renders static half-circle symbol for in_progress items when isRunning is false', () => {
    const frame = renderCard(makeBoard([makeItem('T1', 'Work in progress', 'in_progress')]), false);

    expect(frame).toContain('◐');
    expect(frame).toContain('Work in progress');
    expect(frame).not.toContain('ACTIVE');
  });

  it('safely handles progress bar clamping without RangeError', () => {
    // 0 items
    expect(renderCard(makeBoard([]))).toBe('');

    // 100% complete with custom high counts
    const items = Array.from({ length: 12 }, (_, i) => makeItem(`T${i + 1}`, `Item ${i + 1}`, 'done'));
    const frame = renderCard(makeBoard(items));
    expect(frame).toContain('100%');
    expect(frame).toContain('[██████████]');
  });

  it('renders symbol-only stage column with no badge words or sub-rows', () => {
    const itemWithNotes: TodoItem = {
      ...makeItem('T1', 'Inspect code', 'in_progress'),
      notes: 'verified constants match assertion',
      depends_on: ['T0'],
    };
    const frame = renderCard(
      makeBoard([makeItem('T0', 'Prerequisite', 'done'), itemWithNotes, makeItem('T2', 'Synthesize results', 'todo')]),
      false,
    );

    expect(frame).toContain('✔');
    expect(frame).toContain('◐');
    expect(frame).toContain('○');
    expect(frame).not.toContain('DONE');
    expect(frame).not.toContain('ACTIVE');
    expect(frame).not.toContain('PENDING');
    expect(frame).not.toContain('└ Note: verified constants match assertion');
    expect(frame).not.toContain('└ Depends on: T0');
  });

  it('falls back to pending ○ for unknown wire statuses instead of a blank cell', () => {
    const frame = renderCard(makeBoard([makeItem('T9', 'Mystery task', 'pending' as unknown as TodoStatus)]));
    expect(frame).toContain('Mystery task');
    expect(frame).toMatch(/1\s+Mystery task\s+○/);
  });

  it('keeps the status symbol visible on narrow terminals when the title truncates', () => {
    const longTitle = 'Build the HRMS employee onboarding module with a payroll engine and leave management';
    const frame = frameForNarrow(makeBoard([makeItem('T1', longTitle, 'done')]), 40);
    expect(frame).toContain('…');
    expect(frame).not.toContain(longTitle);
    expect(frame).toContain('✔');
    expect(frame).toMatch(/1\s+Build the HRMS/);
  });

  it('renders live sub-stage execution line when running with activeActivity', () => {
    const { lastFrame } = render(
      <ThemeProvider>
        <PinnedTodoCard
          event={makeBoard([makeItem('T1', 'Audit task', 'in_progress')])}
          isRunning={true}
          activeActivity={{ label: 'file_read (server/config/constants/tools.py)', percent: 50 }}
        />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    expect(frame).toContain('↳');
    expect(frame).toContain('file_read (server/config/constants/tools.py)');
    expect(frame).toContain('(50%)');
  });
});
