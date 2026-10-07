/**
 * Terminal-dimension stubs for render tests.
 *
 * Two things must agree or a component computes its layout for one width and
 * renders into another:
 *   - `process.stdout.columns/rows`, which `useTerminalDimensions` reads;
 *   - the Ink `Stdout` it writes frames through. `ink-testing-library` hardcodes
 *     that at 100 columns (node_modules/ink-testing-library/build/index.js), so
 *     width assertions built on it are measuring the wrong canvas.
 *
 * Cleanup is registered with `onTestFinished`, so a failing assertion cannot
 * leak the stub into the next test.
 */
import { EventEmitter } from 'node:events';
import { render as inkRender } from 'ink';
import { onTestFinished } from 'vitest';

interface StdoutOverride {
  columns?: number;
  rows?: number;
}

/** Minimal Ink stdout: a frame sink whose dimensions we control. */
class FixedStdout extends EventEmitter {
  readonly columns: number;
  readonly rows: number;
  readonly frames: string[] = [];
  private last: string | undefined;

  constructor(columns: number, rows: number) {
    super();
    this.columns = columns;
    this.rows = rows;
  }

  write(frame: string) {
    this.frames.push(frame);
    this.last = frame;
  }

  lastFrame() {
    return this.last;
  }
}

class FixedStderr extends EventEmitter {
  write() {}
}

class FixedStdin extends EventEmitter {
  isTTY = true;
  setRawMode() {}
  setEncoding() {}
  resume() {}
  pause() {}
  ref() {}
  unref() {}
  read() {
    return null;
  }
}

function stubStdoutProperty(prop: 'columns' | 'rows', value: number): () => void {
  const original = Object.getOwnPropertyDescriptor(process.stdout, prop);
  Object.defineProperty(process.stdout, prop, { configurable: true, get: () => value });
  return () => {
    if (original) Object.defineProperty(process.stdout, prop, original);
    else delete (process.stdout as Record<string, unknown>)[prop];
  };
}

/**
 * Render at a specific terminal size, with the layout input and the Ink canvas
 * set to the same width. Unmount and restore happen even on failure.
 */
export function renderAtWidth(node: React.ReactElement, { columns = 80, rows = 24 }: StdoutOverride = {}) {
  const restoreColumns = stubStdoutProperty('columns', columns);
  const restoreRows = stubStdoutProperty('rows', rows);
  const stdout = new FixedStdout(columns, rows);
  const instance = inkRender(node, {
    stdout: stdout as never,
    stderr: new FixedStderr() as never,
    stdin: new FixedStdin() as never,
    exitOnCtrlC: false,
    patchConsole: false,
  });
  onTestFinished(() => {
    instance.unmount();
    restoreColumns();
    restoreRows();
  });
  return {
    ...instance,
    frames: stdout.frames,
    lastFrame: () => stdout.lastFrame(),
  };
}

/** Stub only `process.stdout.columns` — for pure `computeXxx(input)` unit tests. */
export function stubColumns(columns: number): () => void {
  const restore = stubStdoutProperty('columns', columns);
  onTestFinished(restore);
  return restore;
}
