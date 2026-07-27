"""Command safety — detects risky shell commands and requests user confirmation."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class RiskAssessment:
    """Result of a command safety check."""
    is_risky: bool
    reason: str
    risk_level: str  # "safe", "low", "medium", "high"


# High-risk patterns: destructive, irreversible, or system-level commands
_HIGH_RISK_PATTERNS: list[tuple[str, str]] = [
    # Destructive file operations
    (r'\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\b', 'Recursive force delete'),
    (r'\brm\s+-rf\b', 'Recursive force delete'),
    (r'\brm\s+-fr\b', 'Recursive force delete'),
    (r'\brmdir\b.*\*/', 'Directory removal with wildcard'),
    (r'\bdel\s+/[sfq]\b', 'Windows force delete'),
    (r'\bformat\s+[a-zA-Z]:', 'Disk formatting'),
    # System-level changes
    (r'\bchmod\s+777\b', 'World-writable permissions'),
    (r'\bchmod\s+-R\s+777\b', 'Recursive world-writable permissions'),
    (r'\bchown\s+.*\s+/', 'Changing ownership of root paths'),
    (r'\bsudo\s+rm\b', 'Sudo delete operation'),
    (r'\bsudo\s+chmod\b', 'Sudo permission change'),
    (r'\bsudo\s+chown\b', 'Sudo ownership change'),
    # Remote code execution
    (r'curl\b.*\|\s*(ba)?sh', 'Piping remote content to shell'),
    (r'wget\b.*\|\s*(ba)?sh', 'Piping remote content to shell'),
    (r'curl\b.*\|\s*sudo\s+(ba)?sh', 'Sudo piping remote content to shell'),
    # System power
    (r'\bshutdown\b', 'System shutdown'),
    (r'\breboot\b', 'System reboot'),
    (r'\bhalt\b', 'System halt'),
    # Network destructive
    (r'\biptables\s+-F\b', 'Flushing firewall rules'),
    (r'\buterdown\b', 'Firewall shutdown'),
]

# Medium-risk patterns: common but worth confirming
_MEDIUM_RISK_PATTERNS: list[tuple[str, str]] = [
    # Package management (can change system state)
    (r'\bnpm\s+install\s+-g\b', 'Global npm install'),
    (r'\bpip\s+install\b', 'Python package install'),
    (r'\bpip3\s+install\b', 'Python package install'),
    (r'\bgem\s+install\b', 'Ruby gem install'),
    (r'\bapt\s+(install|remove)\b', 'System package change'),
    (r'\byum\s+(install|remove)\b', 'System package change'),
    # Git operations that modify history
    (r'\bgit\s+push\s+.*--force\b', 'Force push to remote'),
    (r'\bgit\s+push\s+.*-f\b', 'Force push to remote'),
    (r'\bgit\s+reset\s+--hard\b', 'Hard reset (loses changes)'),
    (r'\bgit\s+clean\s+-fd\b', 'Git clean untracked files'),
    # Environment/config changes
    (r'\bexport\b.*=.*', 'Environment variable change'),
    (r'\bset\s+[A-Z_]+=.*', 'Environment variable change'),
]

# Low-risk patterns: informational, worth noting
_LOW_RISK_PATTERNS: list[tuple[str, str]] = [
    (r'\bnpm\s+run\s+build\b', 'Build command'),
    (r'\bnpm\s+run\s+dev\b', 'Dev server start'),
    (r'\bpython\s+.*\.py\b', 'Python script execution'),
    (r'\bnode\s+.*\.js\b', 'Node script execution'),
]


def assess_command(command: str) -> RiskAssessment:
    """Assess the risk level of a shell command.

    Returns a RiskAssessment with is_risky=True if the command matches
    any high or medium risk pattern.
    """
    normalized = command.strip().lower()

    for pattern, reason in _HIGH_RISK_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return RiskAssessment(is_risky=True, reason=reason, risk_level="high")

    for pattern, reason in _MEDIUM_RISK_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return RiskAssessment(is_risky=True, reason=reason, risk_level="medium")

    return RiskAssessment(is_risky=False, reason="", risk_level="safe")
