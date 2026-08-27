"""Probe C: launch TUI alone, tee its output, watch TCP + frames."""

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from e2e_full_stack_test import RUN_DIR, find_pid_by_commandline_token  # noqa: E402

CREATE_NEW_CONSOLE = 0x10
FE_MARKER = "DIAG_FE_TOKEN"


def main() -> int:
    fe_log = RUN_DIR / "fe_live.log"
    tsx_cmd = REPO / "node_modules" / ".bin" / "tsx.cmd"
    inner = (
        f"$Host.UI.RawUI.WindowTitle='{FE_MARKER}'; cd '{REPO / 'tui'}'; "
        f"& '{tsx_cmd}' src/index.tsx *>&1 | ForEach-Object {{ $_ ; $_ | "
        f"Out-File '{fe_log}' -Append -Encoding utf8 }}"
    )
    proc = subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", inner],
        creationflags=CREATE_NEW_CONSOLE,
        cwd=str(REPO / "tui"),
    )
    time.sleep(4)
    pid = find_pid_by_commandline_token(FE_MARKER)
    print(f"frontend shell pid: {pid}", flush=True)
    try:
        for i in range(6):
            time.sleep(10)
            est = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue "
                    "| Where-Object RemotePort -eq 8765 | Measure-Object).Count",
                ],
                capture_output=True,
                text=True,
            ).stdout.strip()
            blob = ""
            if fe_log.exists():
                blob = fe_log.read_text(encoding="utf-8", errors="replace")
                lines = [ln.strip() for ln in blob.splitlines() if ln.strip()]
                print(
                    f"t={10 * (i + 1)}s tcp_to_8765={est} fe_log_lines={len(lines)} "
                    f"alive={proc.poll() is None}",
                    flush=True,
                )
                for ln in lines[:14]:
                    print(f"  | {ln[:150]}", flush=True)
            else:
                print(
                    f"t={10 * (i + 1)}s tcp={est} no fe_log yet alive={proc.poll() is None}",
                    flush=True,
                )
            if int(est or 0) > 0:
                print("TCP ESTABLISHED ✔", flush=True)
                return 0
        return 1
    finally:
        kill_tree(proc.pid)


def kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


if __name__ == "__main__":
    sys.exit(main())
