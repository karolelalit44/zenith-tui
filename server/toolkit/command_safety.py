"""Command safety assessment — permission-tier model.

Instead of regex-based command filtering (which is brittle and blocks legitimate
pipes), this module implements a permission-tier system inspired by Claude Code
and Codex:

1. **Read-only commands** auto-approve (ls, cat, grep, git status, etc.)
2. **Workspace-write commands** allow writing within the workspace
3. **Network commands** are blocked by default (curl, wget, ssh, etc.)
4. **Destructive commands** are blocked (rm -rf, format, etc.)

The sandbox layer (not yet implemented) enforces filesystem and network
boundaries. This module provides the approval policy that sits on top.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RiskAssessment:
    is_risky: bool
    reason: str
    risk_level: str  # "safe", "low", "medium", "high"
    requires_approval: bool = False
    tier: str = "read_only"  # "read_only", "workspace_write", "network", "destructive"


# ── Read-only commands (auto-approve) ──────────────────────────────────────
# These are safe to run without approval in any sandbox mode.
READ_ONLY_COMMANDS: set[str] = {
    # File listing / inspection
    "ls",
    "dir",
    "tree",
    "find",
    "locate",
    "which",
    "where",
    "type",
    "file",
    "stat",
    "du",
    "df",
    "wc",
    # File content reading
    "cat",
    "head",
    "tail",
    "less",
    "more",
    # Text processing (read-only)
    "grep",
    "egrep",
    "fgrep",
    "rg",
    "ag",
    "ack",
    "sed",
    "awk",
    "sort",
    "uniq",
    "cut",
    "tr",
    "tee",
    "xargs",
    # Python/Node read-only
    "python",
    "python3",
    "node",
    "deno",
    "bun",
    "go",
    "cargo",
    "rustc",
    "npm",
    "npx",
    "yarn",
    "pnpm",
    "pip",
    "pip3",
    # System info
    "echo",
    "printf",
    "date",
    "whoami",
    "hostname",
    "pwd",
    "env",
    "printenv",
    "set",
    "uname",
    "uptime",
    "id",
    # Process info
    "ps",
    "top",
    "htop",
    "jobs",
    "fg",
    "bg",
    # PowerShell read-only
    "Get-ChildItem",
    "Get-Content",
    "Get-Item",
    "Select-Object",
    "Where-Object",
    "ForEach-Object",
    "Sort-Object",
    "Measure-Object",
    "Out-String",
    "Format-Table",
    "Format-List",
    "Format-Wide",
    "Get-Unique",
    "Get-Random",
    "Tee-Object",
    "ConvertTo-Json",
    "ConvertFrom-Json",
    "Get-Date",
    "Get-History",
    "Get-Host",
    "Get-Command",
    "Get-Help",
    "Get-Alias",
    "Get-Verb",
}

# Git subcommands that are read-only (no network needed)
_GIT_READONLY_SUBCOMMANDS: set[str] = {
    "status",
    "log",
    "diff",
    "show",
    "branch",  # branch lists
    "tag",
    "describe",
    "blame",
    "shortlog",
    "rev-parse",
    "rev-list",
    "symbolic-ref",
    "ls-files",
    "ls-tree",
    "ls-remote",
    "for-each-ref",
    "name-rev",
}

# Git subcommands that need network
_GIT_NETWORK_SUBCOMMANDS: set[str] = {
    "clone",
    "pull",
    "push",
    "fetch",
    "remote",
}

# ── Network commands (blocked by default) ───────────────────────────────────
# These require explicit approval or sandbox network access.
NETWORK_COMMANDS: set[str] = {
    "curl",
    "wget",
    "httpie",
    "http-prompt",
    "xh",
    "curlie",
    "ssh",
    "scp",
    "sftp",
    "rsync",
    "telnet",
    "nc",
    "ncat",
    "socat",
    "lynx",
    "links",
    "w3m",
    "elinks",
    "aria2c",
    "axel",
    "git",  # git clone/pull/push need network
}

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

# ── Medium-risk patterns (require approval) ─────────────────────────────────
_MEDIUM_RISK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bnpm\s+install\s+-g\b", re.IGNORECASE), "Global npm install"),
    (re.compile(r"\bnpm\s+install\s+--global\b", re.IGNORECASE), "Global npm install"),
    (re.compile(r"\bpip\s+install\b", re.IGNORECASE), "Python package install"),
    (re.compile(r"\bpip3\s+install\b", re.IGNORECASE), "Python package install"),
    (re.compile(r"\bgem\s+install\b", re.IGNORECASE), "Ruby gem install"),
    (re.compile(r"\bpnpm\s+add\s+-g\b", re.IGNORECASE), "Global pnpm install"),
    (re.compile(r"\byarn\s+global\s+add\b", re.IGNORECASE), "Global yarn install"),
    (re.compile(r"\bcargo\s+install\b", re.IGNORECASE), "Cargo install"),
    (re.compile(r"\bexport\b.*=.*", re.IGNORECASE), "Environment variable change"),
    (re.compile(r"\bset\s+[A-Z_]+=.*", re.IGNORECASE), "Environment variable change"),
]


def _extract_first_command(command: str) -> str:
    """Extract the first command from a pipeline or chain.

    Handles: `cmd1 | cmd2`, `cmd1 && cmd2`, `cmd1 ; cmd2`, `cmd1 || cmd2`
    Returns the leftmost command for safety assessment.
    """
    # Split on chaining operators to get the first command
    for sep in ("&&", "||", ";", "|"):
        if sep in command:
            command = command.split(sep)[0]
    command = command.strip()
    # Extract the program name (handle paths and args)
    try:
        parts = shlex.split(command)
    except ValueError:
        # Fallback for unparseable commands
        parts = command.split()
    if not parts:
        return ""
    # Get the base name (strip path)
    return Path(parts[0]).name


def _extract_command_parts(command: str) -> list[str]:
    """Extract all command parts from a pipeline/chain for full assessment."""
    # Split on chaining operators
    for sep in ("&&", "||", ";"):
        if sep in command:
            command = command.split(sep)[0]
    command = command.strip()
    # Split on pipes
    parts = command.split("|")
    result = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        try:
            tokens = shlex.split(part)
        except ValueError:
            tokens = part.split()
        if tokens:
            result.append(Path(tokens[0]).name)
    return result


def _is_read_only_command(cmd: str) -> bool:
    """Check if the command is a known read-only command."""
    return cmd in READ_ONLY_COMMANDS


def _is_network_command(cmd: str) -> bool:
    """Check if the command requires network access."""
    return cmd in NETWORK_COMMANDS


def _is_destructive_command(cmd: str) -> bool:
    """Check if the command is destructive and should be blocked."""
    return cmd in DESTRUCTIVE_COMMANDS


def _assess_git_subcommand(command: str) -> str:
    """Assess a git command based on its subcommand.

    Returns: 'read_only', 'network', or 'destructive'
    """
    parts = command.strip().split()
    if len(parts) < 2:
        return "network"  # bare `git` — treat as network
    subcmd = parts[1]
    if subcmd in _GIT_READONLY_SUBCOMMANDS:
        return "read_only"
    if subcmd in _GIT_NETWORK_SUBCOMMANDS:
        return "network"
    # Unknown git subcommand — default to network (safe)
    return "network"




def assess_command(command: str) -> RiskAssessment:
    """Assess the risk level of a command.

    Returns a RiskAssessment with:
    - is_risky: whether the command should be blocked or require approval
    - reason: human-readable reason
    - risk_level: "safe", "low", "medium", "high"
    - requires_approval: whether the command needs user approval
    - tier: the permission tier ("read_only", "workspace_write", "network", "destructive")
    """
    if not command or not command.strip():
        return RiskAssessment(is_risky=False, reason="", risk_level="safe", tier="read_only")

    cmd = _extract_first_command(command)
    normalized = command.strip().lower()

    # 1. Destructive commands — always blocked
    if _is_destructive_command(cmd):
        return RiskAssessment(
            is_risky=True,
            reason=f"Command '{cmd}' is destructive and blocked",
            risk_level="high",
            tier="destructive",
        )

    # 2. Check dangerous patterns (rm -rf, curl | sh, etc.)
    for pattern, reason in _DANGEROUS_PATTERNS:
        if pattern.search(normalized):
            return RiskAssessment(
                is_risky=True,
                reason=reason,
                risk_level="high",
                tier="destructive",
            )

    # 3. Git subcommands — assess based on subcommand
    if cmd == "git":
        git_tier = _assess_git_subcommand(command)
        if git_tier == "read_only":
            return RiskAssessment(is_risky=False, reason="", risk_level="safe", tier="read_only")
        elif git_tier == "network":
            return RiskAssessment(
                is_risky=True,
                reason="Git command requires network access",
                risk_level="medium",
                requires_approval=True,
                tier="network",
            )

    # 4. Pipeline assessment: if ALL commands in the pipe are read-only, the
    #    entire pipeline is read-only (e.g. `Get-ChildItem | Select-Object`).
    pipe_cmds = _extract_command_parts(command)
    if len(pipe_cmds) > 1:
        all_read_only = all(_is_read_only_command(c) for c in pipe_cmds)
        if all_read_only:
            return RiskAssessment(is_risky=False, reason="", risk_level="safe", tier="read_only")

    # 5. Network commands — require approval (not blocked, just gated)
    if _is_network_command(cmd):
        return RiskAssessment(
            is_risky=True,
            reason=f"Command '{cmd}' requires network access",
            risk_level="medium",
            requires_approval=True,
            tier="network",
        )

    # 6. Medium-risk patterns — require approval
    for pattern, reason in _MEDIUM_RISK_PATTERNS:
        if pattern.search(normalized):
            return RiskAssessment(
                is_risky=True,
                reason=reason,
                risk_level="medium",
                requires_approval=True,
                tier="workspace_write",
            )

    # 7. Read-only commands — auto-approve
    if _is_read_only_command(cmd):
        return RiskAssessment(
            is_risky=False,
            reason="",
            risk_level="safe",
            tier="read_only",
        )

    # 8. Unknown commands — treat as workspace_write (allow but log)
    return RiskAssessment(
        is_risky=False,
        reason="",
        risk_level="safe",
        tier="workspace_write",
    )
