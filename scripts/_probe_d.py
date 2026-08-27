"""Probe D: fully native TUI window (no pipes), readiness via TCP to :8765."""

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

CREATE_NEW_CONSOLE = 0x10


def descendants(pid: int, depth: int = 4) -> set[int]:
    out = {pid}
    frontier = [pid]
    for _ in range(depth):
        nxt: list[int] = []
        for p in frontier:
            r = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f'(Get-CimInstance Win32_Process -Filter "ParentProcessId={p}").ProcessId',
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            for tok in r.stdout.split():
                if tok.isdigit():
                    q = int(tok)
                    if q not in out:
                        out.add(q)
                        nxt.append(q)
        frontier = nxt
        if not frontier:
            break
    return out


def ws_established_count(pids: set[int]) -> int:
    ps = (
        "$conns = Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue "
        "| Where-Object { $_.RemotePort -eq 8765 }; "
        "if ($conns) { $conns | ForEach-Object { $_.OwningProcess } } else { -1 }"
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=25
    )
    owners = {int(x) for x in r.stdout.split() if x.strip().lstrip("-").isdigit()}
    return len(owners & pids)


def main() -> int:
    clean_env = {k: v for k, v in __import__("os").environ.items() if k not in ("CI", "TERM")}
    clean_env.setdefault("TERM", "xterm-256color")
    tsx_cmd = REPO / "node_modules" / ".bin" / "tsx.cmd"
    inner = (
        f"$Host.UI.RawUI.WindowTitle='DIAG_NATIVE'; cd '{REPO / 'tui'}'; "
        f"& '{tsx_cmd}' src/index.tsx"
    )
    proc = subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", inner],
        creationflags=CREATE_NEW_CONSOLE,
        cwd=str(REPO / "tui"),
        env=clean_env,
    )
    try:
        for t in range(10, 71, 10):
            time.sleep(10)
            pids = descendants(proc.pid)
            n = ws_established_count(pids)
            print(
                f"t={t}s alive={proc.poll() is None} descendant_pids={len(pids)} ws_conns={n}",
                flush=True,
            )
            if n > 0:
                print("WEBSOCKET ESTABLISHED ✔ — native launch works", flush=True)
                return 0
        print("no websocket within 70s — native launch also hangs", flush=True)
        return 1
    finally:
        kill_tree(proc.pid)


def kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


if __name__ == "__main__":
    sys.exit(main())
