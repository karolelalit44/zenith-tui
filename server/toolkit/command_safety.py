"""Destructive-command blocking for the shell tools.

Zenith performs **no** permission gating. Nothing is "gated", "approved", or
assigned a permission tier: the only rule that executes is a hard block on
destructive commands, enforced by
:class:`~server.toolkit.middleware.safety.SafetyCheckMiddleware`.

Refusal here is name- and pattern-based, not a sandbox. There is no filesystem
or network jail behind it — see the "Explicitly Out of Scope" table in
``ISSUE/RUNTIME_ANALYSIS_ISSUES.md``.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RiskAssessment:
    """Verdict for one shell command.

    ``is_destructive`` is the only field any caller reads. It is deliberately
    the sole verdict: this module models "blocked or not", not a permission
    level, because nothing downstream acts on a finer distinction.
    """

    is_destructive: bool
    reason: str = ""


# ── Destructive commands (always blocked) ───────────────────────────────────
DESTRUCTIVE_COMMANDS: set[str] = {
    "dd",
    "mkfs",
    "fdisk",
    "parted",
    "mount",
    "umount",
    "format",
    "diskpart",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "iptables",
    "ip",
    "ifconfig",
    "netstat",
    "pfctl",
    "route",
    "ufw",
    "firewall-cmd",
    "systemctl",
    "service",
    "chkconfig",
    "crontab",
    "at",
    "batch",
    "doas",
    "su",
    "sudo",
    "apk",
    "apt",
    "apt-cache",
    "apt-get",
    "dnf",
    "dpkg",
    "emerge",
    "home-manager",
    "makepkg",
    "opkg",
    "pacman",
    "paru",
    "pkg",
    "pkg_add",
    "pkg_delete",
    "portage",
    "rpm",
    "yay",
    "yum",
    "zypper",
    "alias",
}

# ── Dangerous command patterns (regex) ──────────────────────────────────────
# Only truly dangerous patterns — not pipe/chaining detection.
_DANGEROUS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\b", re.IGNORECASE), "Recursive force delete"),
    (re.compile(r"\bdel\s+/[sfq]\b", re.IGNORECASE), "Windows force delete"),
    (re.compile(r"\bchmod\s+777\b", re.IGNORECASE), "World-writable permissions"),
    (re.compile(r"\bchmod\s+-R\s+777\b", re.IGNORECASE), "Recursive world-writable permissions"),
    (re.compile(r"\bchown\s+.*\s+/", re.IGNORECASE), "Changing ownership of root paths"),
    (re.compile(r"curl\b.*\|\s*(ba)?sh\b", re.IGNORECASE), "Piping remote content to shell"),
    (re.compile(r"wget\b.*\|\s*(ba)?sh\b", re.IGNORECASE), "Piping remote content to shell"),
    (re.compile(r"curl\b.*\|\s*sudo\s+(ba)?sh\b", re.IGNORECASE), "Sudo piping remote content to shell"),
    (re.compile(r"\bgit\s+push\s+.*--force\b", re.IGNORECASE), "Force push to remote"),
    (re.compile(r"\bgit\s+push\s+.*-f\b", re.IGNORECASE), "Force push to remote"),
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE), "Hard reset (loses changes)"),
    (re.compile(r"\bgit\s+clean\s+-fd\b", re.IGNORECASE), "Git clean untracked files"),
    (re.compile(r"\bgit\s+checkout\s+.*\s+--force\b", re.IGNORECASE), "Force checkout (discards changes)"),
]


def _extract_first_command(command: str) -> str:
    """Extract the program name from a pipeline or chain.

    Handles: `cmd1 | cmd2`, `cmd1 && cmd2`, `cmd1 ; cmd2`, `cmd1 || cmd2`.
    Returns the base name of the leftmost program, without its path.
    """
    for sep in ("&&", "||", ";", "|"):
        if sep in command:
            command = command.split(sep)[0]
    command = command.strip()
    try:
        parts = shlex.split(command)
    except ValueError:
        # Fallback for unparseable commands
        parts = command.split()
    if not parts:
        return ""
    return Path(parts[0]).name


def _is_destructive_command(cmd: str) -> bool:
    """True when *cmd* is a known destructive program."""
    return cmd in DESTRUCTIVE_COMMANDS


def assess_command(command: str) -> RiskAssessment:
    """Report whether *command* is destructive and must be blocked.

    This is a block/no-block decision, nothing more. Network access, package
    installs and environment mutation are all permitted; they are not modelled
    here because no caller would act on such a verdict.
    """
    if not command or not command.strip():
        return RiskAssessment(is_destructive=False)

    cmd = _extract_first_command(command)

    if _is_destructive_command(cmd):
        return RiskAssessment(
            is_destructive=True,
            reason=f"Command '{cmd}' is destructive and blocked",
        )

    normalized = command.strip().lower()
    for pattern, reason in _DANGEROUS_PATTERNS:
        if pattern.search(normalized):
            return RiskAssessment(is_destructive=True, reason=reason)

    return RiskAssessment(is_destructive=False)
