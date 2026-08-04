from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class RiskAssessment:
    is_risky: bool
    reason: str
    risk_level: str


BANNED_COMMANDS: list[str] = [
    "alias",
    "aria2c",
    "axel",
    "chrome",
    "curl",
    "curlie",
    "firefox",
    "http-prompt",
    "httpie",
    "links",
    "lynx",
    "nc",
    "safari",
    "scp",
    "ssh",
    "telnet",
    "w3m",
    "wget",
    "xh",
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
    "at",
    "batch",
    "chkconfig",
    "crontab",
    "fdisk",
    "mkfs",
    "mount",
    "parted",
    "service",
    "systemctl",
    "umount",
    "firewall-cmd",
    "ifconfig",
    "ip",
    "iptables",
    "netstat",
    "pfctl",
    "route",
    "ufw",
]


def _check_command_chaining(command: str) -> bool:
    return bool(re.search("&&|\\|\\||;|\\|", command))


def _is_prefix_of_any(cmd: str, commands: list[str]) -> bool:
    for banned in commands:
        if cmd == banned or cmd.startswith((banned + " ", banned + "-")):
            return True
    return False


_HIGH_RISK_PATTERNS: list[tuple[str, str]] = [
    ("\\brm\\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\\b", "Recursive force delete"),
    ("\\brm\\s+-rf\\b", "Recursive force delete"),
    ("\\brm\\s+-fr\\b", "Recursive force delete"),
    ("\\brmdir\\b.*\\*/", "Directory removal with wildcard"),
    ("\\bdel\\s+/[sfq]\\b", "Windows force delete"),
    ("\\bformat\\s+[a-zA-Z]:", "Disk formatting"),
    ("\\bchmod\\s+777\\b", "World-writable permissions"),
    ("\\bchmod\\s+-R\\s+777\\b", "Recursive world-writable permissions"),
    ("\\bchown\\s+.*\\s+/", "Changing ownership of root paths"),
    ("\\bsudo\\s+rm\\b", "Sudo delete operation"),
    ("\\bsudo\\s+chmod\\b", "Sudo permission change"),
    ("\\bsudo\\s+chown\\b", "Sudo ownership change"),
    ("curl\\b.*\\|\\s*(ba)?sh", "Piping remote content to shell"),
    ("wget\\b.*\\|\\s*(ba)?sh", "Piping remote content to shell"),
    ("curl\\b.*\\|\\s*sudo\\s+(ba)?sh", "Sudo piping remote content to shell"),
    ("\\bshutdown\\b", "System shutdown"),
    ("\\breboot\\b", "System reboot"),
    ("\\bhalt\\b", "System halt"),
    ("\\biptables\\s+-F\\b", "Flushing firewall rules"),
    ("\\buterdown\\b", "Firewall shutdown"),
]
_MEDIUM_RISK_PATTERNS: list[tuple[str, str]] = [
    ("\\bnpm\\s+install\\s+-g\\b", "Global npm install"),
    ("\\bnpm\\s+install\\s+--global\\b", "Global npm install"),
    ("\\bpip\\s+install\\b", "Python package install"),
    ("\\bpip3\\s+install\\b", "Python package install"),
    ("\\bgem\\s+install\\b", "Ruby gem install"),
    ("\\bapt\\s+(install|remove)\\b", "System package change"),
    ("\\byum\\s+(install|remove)\\b", "System package change"),
    ("\\bpnpm\\s+add\\s+-g\\b", "Global pnpm install"),
    ("\\byarn\\s+global\\s+add\\b", "Global yarn install"),
    ("\\bcargo\\s+install\\b", "Cargo install"),
    ("\\bgit\\s+push\\s+.*--force\\b", "Force push to remote"),
    ("\\bgit\\s+push\\s+.*-f\\b", "Force push to remote"),
    ("\\bgit\\s+reset\\s+--hard\\b", "Hard reset (loses changes)"),
    ("\\bgit\\s+clean\\s+-fd\\b", "Git clean untracked files"),
    ("\\bgit\\s+checkout\\s+.*\\s+--force\\b", "Force checkout (discards changes)"),
    ("\\bexport\\b.*=.*", "Environment variable change"),
    ("\\bset\\s+[A-Z_]+=.*", "Environment variable change"),
]
_LOW_RISK_PATTERNS: list[tuple[str, str]] = [
    ("\\bnpm\\s+run\\s+build\\b", "Build command"),
    ("\\bnpm\\s+run\\s+dev\\b", "Dev server start"),
    ("\\bnpm\\s+run\\s+test\\b", "Test command"),
    ("\\bnpx\\b", "npx command execution"),
    ("\\bpython\\s+.*\\.py\\b", "Python script execution"),
    ("\\bpython3\\s+.*\\.py\\b", "Python script execution"),
    ("\\bnode\\s+.*\\.js\\b", "Node script execution"),
    ("\\bgo\\s+run\\b", "Go run command"),
    ("\\bcargo\\s+run\\b", "Cargo run command"),
    ("\\bcargo\\s+build\\b", "Cargo build command"),
    ("\\bcargo\\s+test\\b", "Cargo test command"),
]


def is_command_banned(command: str) -> str | None:
    first_cmd = command.strip().split()[0] if command.strip() else ""
    first_cmd = first_cmd.split("/")[-1]
    if _is_prefix_of_any(first_cmd, BANNED_COMMANDS):
        return first_cmd
    return None


def assess_command(command: str) -> RiskAssessment:
    normalized = command.strip().lower()
    banned = is_command_banned(command)
    if banned:
        return RiskAssessment(
            is_risky=True, reason=f"Command '{banned}' is not allowed", risk_level="high"
        )
    for pattern, reason in _HIGH_RISK_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return RiskAssessment(is_risky=True, reason=reason, risk_level="high")
    for pattern, reason in _MEDIUM_RISK_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return RiskAssessment(is_risky=True, reason=reason, risk_level="medium")
    return RiskAssessment(is_risky=False, reason="", risk_level="safe")
