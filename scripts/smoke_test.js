/**
 * Smoke test: uses node-pty to spawn the TUI, type "Hi", capture all output.
 *
 * Usage:
 *   node scripts/smoke_test.js
 *   node scripts/smoke_test.js --prompt "explain compaction"
 *   node scripts/smoke_test.js --wait 8000
 */

const pty = require("node-pty");
const { spawn, execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const WORKSPACE = path.resolve(__dirname, "..");
const LOG_DIR = WORKSPACE;

// Parse args
const args = process.argv.slice(2);
function getArg(name, fallback) {
  const idx = args.indexOf(name);
  return idx !== -1 && args[idx + 1] ? args[idx + 1] : fallback;
}
const PROMPT = getArg("--prompt", "Hi");
const WAIT_BEFORE_INPUT = parseInt(getArg("--wait", "12000"), 10);
const RESPONSE_TIMEOUT = parseInt(getArg("--timeout", "60000"), 10);

const logFile = path.join(LOG_DIR, `smoke_test_${timestamp()}.log`);
const logLines = [];

function timestamp() {
  const d = new Date();
  return (
    d.getFullYear().toString() +
    String(d.getMonth() + 1).padStart(2, "0") +
    String(d.getDate()).padStart(2, "0") + "_" +
    String(d.getHours()).padStart(2, "0") +
    String(d.getMinutes()).padStart(2, "0") +
    String(d.getSeconds()).padStart(2, "0")
  );
}

function logTime() {
  const d = new Date();
  return (
    String(d.getHours()).padStart(2, "0") + ":" +
    String(d.getMinutes()).padStart(2, "0") + ":" +
    String(d.getSeconds()).padStart(2, "0") + "." +
    String(d.getMilliseconds()).padStart(3, "0")
  );
}

function log(msg = "") {
  const line = `[${logTime()}] ${msg}`;
  logLines.push(line);
  process.stdout.write(line + "\n");
}

function saveLog() {
  fs.writeFileSync(logFile, logLines.join("\n") + "\n", "utf-8");
}

// Strip ANSI escape codes for clean log
function stripAnsi(str) {
  return str
    // eslint-disable-next-line no-control-regex
    .replace(
      /[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><~]/g,
      ""
    )
    .replace(/\r/g, "");
}

async function main() {
  log("=" .repeat(70));
  log("SMOKE TEST: node-pty TUI automation");
  log(`Prompt : ${PROMPT}`);
  log(`Log    : ${logFile}`);
  log("=" .repeat(70));

  // ── 1. Kill old server ─────────────────────────────────────────────
  log("\n[1/3] Cleaning up old server...");
  try {
    const netstat = execSync("netstat -ano", { encoding: "utf-8", stdio: ["pipe", "pipe", "pipe"] });
    const myPid = process.pid;
    for (const line of netstat.split("\n")) {
      if (line.includes(":8765") && line.includes("LISTENING")) {
        const pid = parseInt(line.trim().split(/\s+/).pop(), 10);
        if (pid && pid !== myPid) {
          try {
            execSync(`taskkill /F /PID ${pid}`, { stdio: "pipe" });
            log(`  Killed old server PID ${pid}`);
          } catch {}
        }
      }
    }
  } catch {}

  // ── 2. Start backend + health check ────────────────────────────────
  log("[2/3] Starting backend server...");
  const venvPy = path.join(WORKSPACE, ".venv", "Scripts", "python.exe");
  const python = fs.existsSync(venvPy) ? venvPy : "python";
  const serverProc = spawn(python, ["-m", "server.main", "serve"], {
    cwd: WORKSPACE,
    stdio: "ignore",
    detached: true,
    windowsHide: true,
  });
  serverProc.unref();
  log(`  Server PID: ${serverProc.pid}`);

  // Health check: poll until server responds or timeout
  const http = require("http");
  const HEALTH_TIMEOUT = 15000;
  const HEALTH_INTERVAL = 500;
  const healthStart = Date.now();
  let ready = false;

  log("  Waiting for server to be ready...");
  while (Date.now() - healthStart < HEALTH_TIMEOUT) {
    try {
      await new Promise((resolve, reject) => {
        const req = http.get("http://127.0.0.1:8765/health", (res) => {
          resolve(res.statusCode);
        });
        req.on("error", reject);
        req.setTimeout(1000, () => { req.destroy(); reject(new Error("timeout")); });
      });
      ready = true;
      break;
    } catch {
      await sleep(HEALTH_INTERVAL);
    }
  }

  if (!ready) {
    log(`  WARNING: Server not ready after ${HEALTH_TIMEOUT}ms, proceeding anyway.`);
  } else {
    log(`  Server ready in ${Date.now() - healthStart}ms.`);
  }

  // ── 3. Spawn TUI via node-pty ──────────────────────────────────────
  log("[3/3] Spawning TUI via node-pty...");

  const shell = process.env.COMSPEC || "cmd.exe";
  // Use npx which is always on PATH
  const batchCmd = `cd /d ${WORKSPACE} && npx tsx tui/src/index.tsx`;
  log(`  Command: ${batchCmd}`);

  const ptyProc = pty.spawn(shell, ["/c", batchCmd], {
    name: "xterm-256color",
    cols: 160,
    rows: 50,
    cwd: WORKSPACE,
    env: { ...process.env, TERM: "xterm-256color" },
  });

  log(`  PTY PID: ${ptyProc.pid}`);
  log(`  Waiting ${WAIT_BEFORE_INPUT}ms for TUI to load...`);

  // Collect all output
  let allOutput = "";
  let cleanOutput = "";
  ptyProc.onData((data) => {
    allOutput += data;
    cleanOutput += stripAnsi(data);
  });

  await sleep(WAIT_BEFORE_INPUT);
  log("  TUI should be loaded.");

  // ── 4. Type prompt ─────────────────────────────────────────────────
  log(`\n--- TYPING: ${PROMPT} ---`);
  ptyProc.write(PROMPT);
  await sleep(300);
  ptyProc.write("\r");  // Enter
  log("  Sent.\n");

  // ── 5. Wait for response ───────────────────────────────────────────
  log(`--- WAITING ${RESPONSE_TIMEOUT}ms FOR RESPONSE ---`);

  const startTime = Date.now();
  let lastLen = 0;
  let stableCount = 0;

  while (Date.now() - startTime < RESPONSE_TIMEOUT) {
    await sleep(1000);
    const currentLen = cleanOutput.length;

    if (currentLen === lastLen) {
      stableCount++;
    } else {
      stableCount = 0;
      lastLen = currentLen;
    }

    // If output stabilized for 8 seconds after we got some content, we're done
    if (stableCount >= 8 && currentLen > 100) {
      log("  Output stabilized — response complete.");
      break;
    }

    const elapsed = Math.round((Date.now() - startTime) / 1000);
    process.stdout.write(`\r  ${elapsed}s / ${Math.round(RESPONSE_TIMEOUT / 1000)}s — ${currentLen} chars...`);
  }
  process.stdout.write("\r" + " ".repeat(60) + "\r");

  // ── 6. Log captured output ─────────────────────────────────────────
  log("\n" + "=".repeat(70));
  log("CAPTURED TUI OUTPUT (clean, no ANSI):");
  log("=".repeat(70));
  log("");

  const lines = cleanOutput.split("\n");
  for (const line of lines) {
    const trimmed = line.trimEnd();
    if (trimmed.length > 0) {
      log(`  ${trimmed}`);
    }
  }

  log("");
  log("=".repeat(70));
  log(`Total: ${cleanOutput.length} chars, ${lines.length} lines`);
  log("=".repeat(70));

  // ── 7. Cleanup ─────────────────────────────────────────────────────
  try { ptyProc.kill(); } catch {}
  try { execSync("taskkill /F /PID " + serverProc.pid, { stdio: "pipe" }); } catch {}
  try { execSync("taskkill /F /IM node.exe /FI \"WINDOWTITLE eq *smoke*\"", { stdio: "pipe" }); } catch {}

  saveLog();

  console.log(`\n${"=".repeat(70)}`);
  console.log(`  LOG FILE: ${logFile}`);
  console.log(`${"=".repeat(70)}\n`);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

main().catch((err) => {
  console.error("FATAL:", err);
  saveLog();
  process.exit(1);
});
