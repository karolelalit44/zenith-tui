#!/usr/bin/env node
/**
 * TUI E2E: Spawns the real TUI via node-pty, types a prompt,
 * waits for completion, prints EVERYTHING to stdout so you can watch.
 *
 * Usage: node scripts/tui_e2e.mjs [--prompt "..."] [--timeout 90]
 */
import { spawn as ptySpawn } from "node-pty";
import { setTimeout as sleep } from "node:timers/promises";
import { existsSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const REPO_ROOT = join(__dirname, "..");

const args = process.argv.slice(2);
const getArg = (name, fallback) => {
  const i = args.indexOf(name);
  return i !== -1 && i + 1 < args.length ? args[i + 1] : fallback;
};
const PROMPT = getArg("--prompt", "What is 2+2? Reply with just the number.");
const TIMEOUT = parseInt(getArg("--timeout", "90"), 10);
const SILENT = args.includes("--silent");

function stripAnsi(s) {
  return s.replace(
    /[\u001B\u009B][[\]()#;?]*(?:\d{1,4}(?:;\d{0,4})*)?[\dA-ORZcf-nq-uy=><~]/g,
    ""
  );
}

function log(msg) {
  if (!SILENT) process.stderr.write(`\x1b[36m[tui-e2e]\x1b[0m ${msg}\n`);
}

async function main() {
  const logDir = join(REPO_ROOT, "scripts", "e2e_logs");
  if (!existsSync(logDir)) mkdirSync(logDir, { recursive: true });

  log(`Starting TUI in PTY (cwd: tui/)`);
  log(`Prompt: "${PROMPT}"`);
  log(`Timeout: ${TIMEOUT}s`);
  log("");

  // Spawn TUI in a real PTY
  const pty = ptySpawn("cmd.exe", ["/k", "npx tsx src/index.tsx"], {
    name: "xterm-256color",
    cols: 160,
    rows: 50,
    cwd: join(REPO_ROOT, "tui"),
    env: { ...process.env, TERM: "xterm-256color" },
  });

  let rawOutput = "";
  let stripped = "";
  const startTime = Date.now();

  // Pipe ALL PTY output to stderr (so you can watch) and collect it
  pty.onData((data) => {
    rawOutput += data;
    const clean = stripAnsi(data);
    stripped += clean;
    // Print every character to stderr so the user sees it
    if (!SILENT) process.stderr.write(data);
  });

  pty.onExit(({ exitCode }) => {
    log(`TUI process exited with code ${exitCode}`);
  });

  // Wait for TUI to become ready
  log("Waiting for TUI to start...");
  const READY = ["Ask anything", "\u276f", "ZENITH"];
  let ready = false;
  while (Date.now() - startTime < TIMEOUT * 1000) {
    for (const m of READY) {
      if (stripped.includes(m)) {
        ready = true;
        break;
      }
    }
    if (ready) break;
    await sleep(200);
  }

  if (!ready) {
    log("ERROR: TUI did not start within timeout");
    pty.kill();
    const report = { success: false, error: "TUI startup timeout" };
    process.stdout.write(JSON.stringify(report));
    process.exit(1);
  }

  const readyMs = Date.now() - startTime;
  log(`TUI ready in ${readyMs}ms`);

  // Clear any existing text in input
  await sleep(300);
  pty.write("\x03"); // Ctrl+C
  await sleep(100);

  // Type the prompt character by character
  log(`Typing prompt: "${PROMPT}"`);
  for (const ch of PROMPT) {
    pty.write(ch);
    await sleep(30 + Math.random() * 30);
  }
  log("Prompt typed, pressing Enter...");
  await sleep(200);
  pty.write("\r");

  // Wait for completion
  const submitTime = Date.now();
  log("Waiting for response...");
  const COMPLETION_RE = /iter\.?s?\s*[\u00b7\u00b8]/;
  const ERROR_RE = /(?:Error|FATAL|Cannot connect)/;
  let completed = false;
  let errored = false;

  while (Date.now() - submitTime < TIMEOUT * 1000) {
    await sleep(300);
    if (COMPLETION_RE.test(stripped)) {
      completed = true;
      break;
    }
    if (ERROR_RE.test(stripped.slice(-2000))) {
      errored = true;
      break;
    }
  }

  const elapsedMs = Date.now() - submitTime;
  log(completed ? `Response completed in ${elapsedMs}ms` : errored ? "Error detected" : "Timeout");

  // Let final output settle
  await sleep(1000);

  // Kill TUI
  pty.kill();

  // Analyze
  const hasCheckmark = rawOutput.includes("\u2713");
  const hasMetrics = COMPLETION_RE.test(stripped);
  const hasError = ERROR_RE.test(stripped);
  const metricsMatch = stripped.match(
    /(\d+)\s*iter\.?s?\s*[\u00b7\u00b8]\s*([\d.]+)s?\s*[\u00b7\u00b8]\s*([\d.]+[kK]?)\s*tokens?/
  );

  // Extract response text
  const promptIdx = stripped.indexOf(PROMPT);
  let responseText = "";
  if (promptIdx !== -1) {
    const after = stripped.slice(promptIdx + PROMPT.length);
    const mIdx = after.search(/iter\.?s?\s*[\u00b7\u00b8]/);
    responseText = (mIdx !== -1 ? after.slice(0, mIdx) : after.slice(0, 3000)).trim();
  }

  const report = {
    success: completed && !hasError,
    prompt: PROMPT,
    readyMs,
    elapsedMs,
    responseText: responseText.slice(0, 3000),
    hasCheckmark,
    hasMetrics,
    hasStreaming: rawOutput.length > 500,
    hasError,
    metrics: metricsMatch
      ? { iterations: metricsMatch[1], seconds: metricsMatch[2], tokens: metricsMatch[3] }
      : null,
    rawOutputLength: rawOutput.length,
    outputLineCount: stripped.split("\n").filter((x) => x.trim()).length,
  };

  // Save logs
  const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  writeFileSync(join(logDir, `tui_raw_${ts}.log`), rawOutput, "utf-8");
  writeFileSync(join(logDir, `tui_report_${ts}.json`), JSON.stringify(report, null, 2), "utf-8");

  log("");
  log("=".repeat(60));
  log(`RESULT: ${report.success ? "SUCCESS" : "FAILURE"}`);
  log(`  Ready in: ${report.readyMs}ms`);
  log(`  Response in: ${report.elapsedMs}ms`);
  log(`  Checkmark: ${report.hasCheckmark}`);
  log(`  Metrics: ${report.hasMetrics}`);
  log(`  Output: ${report.rawOutputLength} bytes, ${report.outputLineCount} lines`);
  if (report.metrics) {
    log(`  Iterations: ${report.metrics.iterations}`);
    log(`  Tokens: ${report.metrics.tokens}`);
  }
  if (report.responseText) {
    log("");
    log("RESPONSE:");
    report.responseText.split("\n").slice(0, 15).forEach((ln) => log("  " + ln));
  }
  log("=".repeat(60));

  // JSON to stdout for Python to parse
  process.stdout.write(JSON.stringify(report));
  process.exit(report.success ? 0 : 1);
}

main().catch((err) => {
  process.stderr.write(`Fatal: ${err.message}\n`);
  process.exit(2);
});
