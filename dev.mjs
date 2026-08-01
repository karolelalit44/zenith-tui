import { spawn } from 'node:child_process';
import { openSync, closeSync, writeSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const logPath = join(root, 'zenith_server.log');
const python = process.env.PYTHON || 'python';

const logFd = openSync(logPath, 'a');
try {
  writeSync(logFd, `\n--- ${new Date().toISOString()} backend starting ---\n`);
} catch {
  /* ignore */
}

console.log('Starting backend: %s -m server.main serve', python);
console.log('Server log: %s', logPath);

const server = spawn(python, ['-m', 'server.main', 'serve'], {
  cwd: root,
  stdio: ['ignore', logFd, logFd],
});

let serverExited = false;
let tuiExited = false;

server.on('exit', (code) => {
  serverExited = true;
  closeSync(logFd);
  if (!tuiExited) {
    console.error('Backend exited early (code %s). Log tail:\n%s', code, readLogTail());
    process.exit(1);
  }
});

server.on('error', (err) => {
  console.error('Failed to start backend: %s', err.message);
  process.exit(1);
});

function readLogTail() {
  try {
    const content = readFileSync(logPath, 'utf8');
    return content.split('\n').slice(-20).join('\n');
  } catch {
    return '(could not read log)';
  }
}

function startTui() {
  console.log('Starting TUI...');
  const tui = spawn('pnpm', ['--filter', 'tui', 'dev'], {
    cwd: root,
    stdio: 'inherit',
    shell: true,
  });
  tui.on('error', (err) => {
    tuiExited = true;
    console.error('Failed to start TUI: %s', err.message);
    server.kill();
    process.exit(1);
  });
  tui.on('exit', (code) => {
    tuiExited = true;
    console.log('TUI exited (code %s). Stopping backend.', code);
    server.kill();
    process.exit(code ?? 0);
  });
}

setTimeout(() => {
  if (serverExited) return;
  startTui();
}, 1200);

function shutdown() {
  if (tuiExited || serverExited) return;
  tuiExited = true;
  server.kill();
  process.exit(0);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
process.on('uncaughtException', (err) => {
  console.error('Unexpected error:', err);
  server.kill();
  process.exit(1);
});
