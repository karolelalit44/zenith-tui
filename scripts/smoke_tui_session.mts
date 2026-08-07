/**
 * Live-stack smoke test driver (single file).
 *
 * Starts the real backend, boots the Ink TUI headless via ink-testing-library,
 * drives three prompts (greeting / topic / implementation) through the real
 * WebSocket transport, and reports tool calls + token/context usage per prompt
 * against the measured tool-schema budget.
 *
 * Run: node node_modules\tsx\dist\cli.mjs scripts\smoke_tui_session.mts
 *
 * Port handling: if a process already answers GET /health on 127.0.0.1:8765 it
 * is reused; otherwise a free port is chosen and the backend is spawned there.
 * Some environments have VS Code forwarding port 8765 (answers 426 to plain
 * HTTP), so the driver never assumes 8765 is reachable.
 *
 * Env overrides:
 *   SMOKE_PORT                 force the backend port
 *   SMOKE_STARTUP_TIMEOUT_MS   wait for backend + TUI ready (default 90000)
 *   SMOKE_TURN_TIMEOUT_MS      wait for a terminal event per prompt (default 300000)
 *
 * Optional:
 *   --model <provider>/<model>  set the model selection before mounting the TUI
 */
import { spawn, type ChildProcess } from 'node:child_process';
import { existsSync } from 'node:fs';
import { unlink } from 'node:fs/promises';
import { createServer } from 'node:net';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { render } from 'ink-testing-library';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const HOST = '127.0.0.1';
const PYTHON = join(ROOT, '.venv', 'Scripts', 'python.exe');

const STARTUP_TIMEOUT_MS = Number(process.env.SMOKE_STARTUP_TIMEOUT_MS ?? '90000');
const TURN_TIMEOUT_MS = Number(process.env.SMOKE_TURN_TIMEOUT_MS ?? '300000');

// Schema-token budgets measured on the live registry (see 01-tool-orchestration).
const SCHEMA_BUDGET = {
  fullRegistryTokens: 1407, // 19 tools, cl100k_base baseline
  buildSeedTokens: 628, // 8-tool build-mode active schema set (gpt-4o)
  planSeedTokens: 476, // 6-tool plan-mode active schema set (gpt-4o)
};

const wait = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

async function fetchJson(base: string, path: string): Promise<any> {
  const res = await fetch(`${base}${path}`);
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return res.json();
}

/** True only if an actual zenith backend answers /health with a ready handler. */
async function probeHealth(base: string): Promise<boolean> {
  try {
    const res = await fetch(`${base}/health`, { signal: AbortSignal.timeout(3000) });
    if (!res.ok) return false;
    const r = (await res.json()) as { status?: string; handler?: boolean };
    return r?.status === 'ok' && !!r.handler;
  } catch {
    return false;
  }
}

function findFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once('error', reject);
    server.listen(0, HOST, () => {
      const address = server.address() as { port: number };
      const port = address.port;
      server.close(() => resolve(port));
    });
  });
}

async function waitForFrame(
  getFrame: () => string,
  predicate: (frame: string) => boolean,
  timeoutMs: number,
): Promise<string> {
  const start = Date.now();
  let frame = getFrame();
  while (!predicate(frame) && Date.now() - start < timeoutMs) {
    await wait(100);
    frame = getFrame();
  }
  return frame;
}

// ── Backend process management ──────────────────────────────────

let backend: ChildProcess | null = null;
let backendOwned = false;

async function ensureBackend(base: string, port: number): Promise<void> {
  if (await probeHealth(base)) {
    console.log('[driver] reusing already-running backend');
    backendOwned = false;
    return;
  }
  if (!existsSync(PYTHON)) throw new Error(`Python not found: ${PYTHON}`);
  console.log(`[driver] starting backend on 127.0.0.1:${port}`);
  backend = spawn(PYTHON, ['-m', 'server.main', 'serve', '--host', HOST, '--port', String(port)], {
    cwd: ROOT,
    env: process.env,
    detached: true,
    windowsHide: false,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  backendOwned = true;
  backend.stdout?.on('data', (d: Buffer) => process.stdout.write(`[backend] ${d}`));
  backend.stderr?.on('data', (d: Buffer) => process.stderr.write(`[backend] ${d}`));

  const deadline = Date.now() + STARTUP_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (await probeHealth(base)) {
      console.log('[driver] backend healthy');
      return;
    }
    if (backend.exitCode !== null) {
      throw new Error(`backend exited early (code ${backend.exitCode})`);
    }
    await wait(500);
  }
  throw new Error('backend did not become healthy in time');
}

async function stopBackend(): Promise<void> {
  if (!backendOwned || !backend) return;
  if (backend.exitCode === null) {
    try {
      backend.kill();
    } catch {}
    await wait(800);
    if (backend.exitCode === null) {
      try {
        spawn('taskkill', ['/pid', String(backend.pid), '/T', '/F'], { stdio: 'ignore' });
      } catch {}
    }
  }
}

// ── Event capture (dedup replayed history by event id) ──────────

interface RawEvent {
  kind: string;
  data: Record<string, unknown>;
  sessionId?: string;
  rpcId: string;
}

interface TurnResult {
  label: string;
  prompt: string;
  outcome: 'success' | 'error';
  iterations?: number;
  tokenInfo: Record<string, unknown>;
  tools: string[];
  eventKinds: string[];
  confirmations: number;
  elapsedMs: number;
}

function isTerminal(e: RawEvent): boolean {
  if (e.kind === 'success') return typeof e.data?.iterations === 'number';
  if (e.kind === 'error') return e.data?.recoverable !== true;
  return false;
}

function findTerminal(log: RawEvent[], from: number): number {
  for (let i = from; i < log.length; i++) {
    if (isTerminal(log[i])) return i;
  }
  return -1;
}

// ── Turn runner ─────────────────────────────────────────────────

async function runTurn(
  app: ReturnType<typeof render>,
  wsClient: { sendConfirmation(id: string, approved: boolean): Promise<void> },
  log: RawEvent[],
  label: string,
  prompt: string,
): Promise<TurnResult> {
  const startIdx = log.length;
  const startedAt = Date.now();
  const confirmations: { id: string; tool: string; seenAt: number; acked: boolean }[] = [];

  app.stdin.write(prompt);
  await wait(300);
  app.stdin.write('\r');
  console.log(`[driver] submitted "${label}" prompt`);

  const deadline = Date.now() + TURN_TIMEOUT_MS;
  let terminalIdx = -1;

  while (Date.now() < deadline) {
    for (let i = startIdx; i < log.length; i++) {
      const e = log[i];
      if (e.kind !== 'confirmation_request') continue;
      const id = String(e.data?.confirmation_id ?? '');
      if (!id) continue;
      const existing = confirmations.find((c) => c.id === id);
      if (!existing) {
        const tool = String(e.data?.tool ?? '');
        console.log(`[driver] confirmation ${id} for "${tool}" — approving via 'y'`);
        app.stdin.write('y');
        confirmations.push({ id, tool, seenAt: Date.now(), acked: true });
      }
    }
    for (const c of confirmations) {
      if (!c.acked && Date.now() - c.seenAt > 6000) {
        c.acked = true;
        console.log(`[driver] confirmation ${c.id} still unanswered — approving over RPC`);
        try {
          await wsClient.sendConfirmation(c.id, true);
        } catch {}
      }
    }
    terminalIdx = findTerminal(log, startIdx);
    if (terminalIdx !== -1) break;
    await wait(200);
  }

  if (terminalIdx === -1) {
    throw new Error(`Turn "${label}" timed out after ${TURN_TIMEOUT_MS}ms (no terminal success/error event)`);
  }

  const slice = log.slice(startIdx, terminalIdx + 1);
  const tools: string[] = [];
  for (const e of slice) {
    if (e.kind === 'tool_call') {
      const name = String(e.data?.tool ?? '');
      if (!tools.includes(name)) tools.push(name);
    }
  }

  const terminal = log[terminalIdx];
  return {
    label,
    prompt,
    outcome: terminal.kind === 'success' ? 'success' : 'error',
    iterations: typeof terminal.data?.iterations === 'number' ? Number(terminal.data.iterations) : undefined,
    tokenInfo: (terminal.data?.tokenInfo ?? {}) as Record<string, unknown>,
    tools,
    eventKinds: [...new Set(slice.map((e) => e.kind))],
    confirmations: confirmations.length,
    elapsedMs: Date.now() - startedAt,
  };
}

// ── Report helpers ──────────────────────────────────────────────

function fmtUsage(t: TurnResult): string {
  const info = t.tokenInfo;
  const get = (k: string, d: string) => (info[k] !== undefined ? String(info[k]) : d);
  return (
    `used=${get('used', '?')}/${get('total', '?')} (${get('percent', '?')})  ` +
    `prompt=${get('prompt_tokens', '?')} completion=${get('completion_tokens', '?')} ` +
    `cached=${get('cached_tokens', '?')} estimated=${get('estimated', '?')} mode=${get('mode', '?')}`
  );
}

function fmtTools(tools: string[]): string {
  return tools.length === 0 ? '(none)' : tools.join(', ');
}

function pass(ok: boolean): string {
  return ok ? 'PASS' : 'FAIL';
}

// ── Main ────────────────────────────────────────────────────────

function parseArgs(argv: string[]): { model?: string } {
  const out: { model?: string } = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--model' && argv[i + 1]) {
      out.model = argv[++i];
    }
  }
  return out;
}

async function main(): Promise<number> {
  const args = parseArgs(process.argv.slice(2));

  // Decide the backend port BEFORE importing TUI modules so appConfig picks it up.
  const forcedPort = Number(process.env.SMOKE_PORT ?? '') || 0;
  const defaultBase = `http://${HOST}:8765`;
  let port: number;
  if (forcedPort) {
    port = forcedPort;
  } else if (await probeHealth(defaultBase)) {
    port = 8765;
  } else {
    port = await findFreePort();
  }
  const BASE = `http://${HOST}:${port}`;
  process.env.ZENITH_BACKEND_URL = BASE;
  console.log(`[driver] repo root: ${ROOT}`);
  console.log(`[driver] backend target: ${BASE}`);

  // TUI modules must be imported after ZENITH_BACKEND_URL is set (appConfig snapshot).
  type JsonRpcEvent = import('../tui/src/services/transport/WebSocketClient').JsonRpcEvent;
  const [{ App }, { ThemeProvider }, { wsClient }] = await Promise.all([
    import('../tui/src/App'),
    import('../tui/src/theme/ThemeContext'),
    import('../tui/src/services/transport/WebSocketClient'),
  ]);

  const rawLog: RawEvent[] = [];
  const seenIds = new Set<string>();
  const unsubEvents = wsClient.onEvent((e: JsonRpcEvent) => {
    const id = e.params.id;
    if (id && seenIds.has(id)) return;
    if (id) seenIds.add(id);
    rawLog.push({ kind: e.params.kind, data: e.params.data ?? {}, sessionId: e.params.session_id, rpcId: id });
  });

  let app: ReturnType<typeof render> | null = null;
  let probePath = '';

  try {
    await ensureBackend(BASE, port);

    if (args.model) {
      const slash = args.model.indexOf('/');
      if (slash <= 0 || slash === args.model.length - 1) {
        throw new Error(`--model expects <provider>/<model>, got "${args.model}"`);
      }
      const providerID = args.model.slice(0, slash);
      const modelID = args.model.slice(slash + 1);
      const res1 = await fetch(`${BASE}/startup/providers/${encodeURIComponent(providerID)}/model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: modelID }),
      });
      if (!res1.ok) throw new Error(`model registration failed: HTTP ${res1.status}`);
      const res2 = await fetch(`${BASE}/startup/model-selection`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current: { providerID, modelID }, recent: [], favorite: [] }),
      });
      if (!res2.ok) throw new Error(`model selection failed: HTTP ${res2.status}`);
      console.log(`[driver] model override -> ${args.model}`);
    }

    const status = await fetchJson(BASE, '/status');
    const toolCount = Array.isArray(status.tools) ? status.tools.length : '?';
    console.log(
      `[driver] status: ready=${status.ready} provider=${status.provider} workspace=${status.workspace} tools=${toolCount}`,
    );

    app = render(React.createElement(ThemeProvider, null, React.createElement(App)));
    console.log('[driver] TUI mounted; waiting for startup...');
    const readyFrame = await waitForFrame(app.lastFrame, (f) => f.includes('❯'), STARTUP_TIMEOUT_MS);
    if (!readyFrame.includes('❯')) {
      throw new Error('TUI did not reach the ready state (no input prompt in frame)');
    }
    console.log('[driver] TUI ready.');

    const stamp = Date.now();
    probePath = join(ROOT, 'scripts', `smoke_probe_${stamp}.txt`);

    const plans = [
      { label: 'greeting', prompt: () => 'Hello' },
      {
        label: 'topic',
        prompt: () => 'In a few words, what does an AI coding assistant do?',
      },
      {
        label: 'implementation',
        prompt: () =>
          `Create a file named scripts/smoke_probe_${stamp}.txt in this workspace containing exactly one line: zenith smoke ok. Use the file_write tool to write the file.`,
      },
    ];

    const turns: TurnResult[] = [];
    for (const plan of plans) {
      const t = await runTurn(app, wsClient, rawLog, plan.label, plan.prompt());
      turns.push(t);
      console.log(`[driver] turn "${t.label}" finished in ${(t.elapsedMs / 1000).toFixed(1)}s: ${t.outcome}`);
      await wait(800);
    }

    let probeOk = false;
    let probeContent = '';
    if (existsSync(probePath)) {
      const { readFile } = await import('node:fs/promises');
      probeContent = (await readFile(probePath, 'utf8')).trim();
      probeOk = probeContent === 'zenith smoke ok';
    }

    // ── Assertions ──
    const checks: { name: string; ok: boolean; detail: string }[] = [
      {
        name: 'backend healthy',
        ok: status.ready === true,
        detail: `ready=${status.ready} tools=${toolCount}`,
      },
    ];
    for (const t of turns) {
      checks.push({
        name: `turn "${t.label}" completed`,
        ok: t.outcome === 'success',
        detail: `outcome=${t.outcome} iterations=${t.iterations ?? '?'}`,
      });
    }
    for (const t of turns) {
      if (t.label === 'greeting' || t.label === 'topic') {
        checks.push({
          name: `turn "${t.label}" uses no tools`,
          ok: t.tools.length === 0,
          detail: `tools=${fmtTools(t.tools)}`,
        });
      }
    }
    const impl = turns.find((t) => t.label === 'implementation');
    const implTools = impl?.tools ?? [];
    checks.push({
      name: 'turn "implementation" calls a build tool',
      ok: implTools.length > 0 && implTools.some((n) => ['file_write', 'file_edit', 'bash'].includes(n)),
      detail: `tools=${fmtTools(implTools)}`,
    });
    checks.push({
      name: 'probe file written',
      ok: probeOk,
      detail: `path=scripts/smoke_probe_${stamp}.txt content="${probeContent || '(missing)'}"`,
    });

    // ── Report ──
    console.log('\n────────────────────────── SMOKE REPORT ──────────────────────────');
    console.log(`backend:   ${BASE}  provider=${status.provider}  tools=${toolCount}`);
    console.log(
      `schema budget:  full registry=${SCHEMA_BUDGET.fullRegistryTokens} tokens (cl100k_base)` +
        `  build seed=${SCHEMA_BUDGET.buildSeedTokens}  plan seed=${SCHEMA_BUDGET.planSeedTokens} (gpt-4o)`,
    );
    for (const t of turns) {
      console.log('');
      console.log(`[${t.label}]`);
      console.log(`  prompt:       ${t.prompt}`);
      console.log(`  outcome:      ${t.outcome}  iterations=${t.iterations ?? '?'}  ${(t.elapsedMs / 1000).toFixed(1)}s`);
      console.log(`  tools:        ${fmtTools(t.tools)}`);
      console.log(`  confirmations:${t.confirmations}`);
      console.log(`  tokenInfo:    ${fmtUsage(t)}`);
      console.log(`  eventKinds:   ${t.eventKinds.join(', ')}`);
    }
    console.log('');
    let failures = 0;
    for (const c of checks) {
      if (!c.ok) failures++;
      console.log(`  [${pass(c.ok)}] ${c.name}  (${c.detail})`);
    }
    console.log('────────────────────────────────────────────────────────────────────');
    console.log(failures === 0 ? 'ALL CHECKS PASSED' : `${failures} check(s) FAILED`);
    return failures === 0 ? 0 : 1;
  } finally {
    if (app) {
      try {
        app.unmount();
      } catch {}
    }
    try {
      unsubEvents();
    } catch {}
    try {
      await wsClient.close();
    } catch {}
    if (probePath && existsSync(probePath)) {
      try {
        await unlink(probePath);
        console.log(`[driver] cleaned up ${probePath}`);
      } catch {}
    }
    await stopBackend();
  }
}

main()
  .then((code) => {
    process.exitCode = code;
  })
  .catch((err) => {
    console.error(`[driver] FAILED: ${err instanceof Error ? err.message : err}`);
    process.exitCode = 1;
  });
