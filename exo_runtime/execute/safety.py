"""Classify a command's blast radius before we run it.

SAFE = strictly read-only diagnostics (status / list / show / cat)
CAUTION = changes ephemeral state (restart a service, reload config)
DESTRUCTIVE = changes persistent state (rm, drop, force-push, dd, format)

Rules are pattern-based with explicit allow-lists. A command not matched by
any explicit allow-list defaults to CAUTION — fail-cautious by default.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class SafetyClass(str, Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DESTRUCTIVE = "destructive"
    UNCLASSIFIED = "unclassified"


# Read-only command patterns. Anchored at start; allows pipes + grep + head/tail/awk.
SAFE_PATTERNS = [
    # Proxmox + LXC diagnostics
    r"^\s*pvesm\s+status",
    r"^\s*pct\s+(status|list|config|exec\s+\d+\s+--\s+(bash|sh)\s+-c\s+['\"][^'\"]*\b(free|df|systemctl\s+status|systemctl\s+--failed|ps|ip|cat)\b)",
    r"^\s*qm\s+(status|list|config)",
    # Linux core diagnostics
    r"^\s*(df|free|uptime|whoami|hostname|id|date)\s*",
    r"^\s*systemctl\s+(status|list-units|list-unit-files|is-active|is-enabled|--failed)",
    r"^\s*journalctl\s+(--no-pager|-n\s+\d+|--since|-u)",
    r"^\s*ps\s+(aux|-ef|-eo|--no-headers)",
    r"^\s*mount\b(?!\s+-(t|o|r|w|U|L)\s+)",  # mount with no flags = read-only listing
    r"^\s*(lsblk|lsmod|lscpu|lspci|lsusb)\b",
    r"^\s*ip\s+(a|r|link|addr|route|s\b)",
    r"^\s*ss\s+-",
    r"^\s*nfsstat\b",
    r"^\s*zpool\s+(status|list|history|iostat|get)",
    r"^\s*zfs\s+(list|get|holds)",
    r"^\s*needrestart\s+-k",
    # File reads
    r"^\s*cat\s+[^>|;&]*$",
    r"^\s*(head|tail|less|more)\s+",
    r"^\s*(ls|find|grep|awk|sed\s+-n|cut|wc|sort|uniq|tr)\b",
    r"^\s*tail\s+-",
    # Network probes (read-only)
    r"^\s*(ping|traceroute|tracert|nslookup|dig|host|curl\s+(-s|--silent|-I|--head|-X\s+(GET|HEAD)))",
    # SSH wrappers that ONLY run safe commands
    r"^\s*ssh\s+\S+\s+['\"](pvesm\s+status|free\s|df\s|uptime|whoami|cat\s|tail\s|head\s|ls\s|grep\s|ps\s|systemctl\s+(status|list|is-)|mount\s*$|hostname|date)",
    # gh / git diagnostics
    r"^\s*git\s+(status|log|diff|show|branch|remote|fetch\s+--dry-run|describe|rev-parse)\b",
    r"^\s*gh\s+(repo\s+view|api\s+/repos|api\s+/orgs|workflow\s+list|run\s+list)\b",
    # docker diagnostics
    r"^\s*docker\s+(ps|images|inspect|info|version|stats\s+--no-stream|exec\s+\S+\s+(cat|head|tail|ls|free|df|ps|systemctl\s+status))",
]

# Patterns that are caution — they change state but reversibly
CAUTION_PATTERNS = [
    r"^\s*systemctl\s+(start|stop|restart|reload|enable|disable)\b",
    r"^\s*service\s+\S+\s+(start|stop|restart|reload)",
    r"^\s*pct\s+(start|stop|reboot|shutdown|reload-config)\b",
    r"^\s*qm\s+(start|stop|reboot|shutdown|reset)\b",
    r"^\s*docker\s+(start|stop|restart|pause|unpause|kill\s+-\s+SIG(USR|HUP))",
    r"^\s*kill\s+(-(HUP|USR1|USR2)|-1\b)",
    r"^\s*apt(-get)?\s+(update|upgrade|--dry-run)\b",  # update is reversible; upgrade with --dry-run
    r"^\s*pip\s+install(\s+--user)?\s+",
    r"^\s*npm\s+(install|update)\b",
]

# Patterns that are explicitly destructive
DESTRUCTIVE_PATTERNS = [
    r"\brm\s+-rf?\b",
    r"\brmdir\b",
    r"\bdd\b\s+if=",
    r"\bmkfs",
    r"\bformat\b",
    r"\bDROP\s+(TABLE|DATABASE|SCHEMA|INDEX)",
    r"\bTRUNCATE\s+TABLE",
    r"\bDELETE\s+FROM",
    r"\bUPDATE\s+\S+\s+SET",
    r"\bgit\s+push\s+(--force|-f)\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\s+-(f|x)",
    r"\bgit\s+branch\s+-D\b",
    r"\bdocker\s+(rm|rmi|volume\s+rm|system\s+prune)",
    r"\bpct\s+destroy\b",
    r"\bqm\s+destroy\b",
    r"\bzfs\s+destroy\b",
    r"\bzpool\s+destroy\b",
    r"\bapt(-get)?\s+(remove|purge|autoremove|--force-)",
    r"\bsystemctl\s+(mask|unmask)\b",
    r"\b>\s*/dev/sd[a-z]",
    r"\b/etc/(passwd|shadow|sudoers)",
]


def classify_command(command: str) -> SafetyClass:
    """Classify a command's blast radius. Fail-cautious on unknown."""
    if not command or not command.strip():
        return SafetyClass.UNCLASSIFIED

    cmd = command.strip()

    # Destructive checked first — even within otherwise-safe wrapping
    for pat in DESTRUCTIVE_PATTERNS:
        if re.search(pat, cmd, flags=re.IGNORECASE):
            return SafetyClass.DESTRUCTIVE

    # Caution: reversible state change
    for pat in CAUTION_PATTERNS:
        if re.search(pat, cmd):
            return SafetyClass.CAUTION

    # Safe: read-only diagnostics
    for pat in SAFE_PATTERNS:
        if re.match(pat, cmd, flags=re.IGNORECASE):
            return SafetyClass.SAFE

    # Fail-cautious: anything unmatched goes to UNCLASSIFIED (treated as
    # caution by the runner — needs explicit consent)
    return SafetyClass.UNCLASSIFIED


def is_runnable_without_explicit_consent(command: str, allow_caution: bool = False) -> bool:
    """In --auto mode, only SAFE commands run without explicit consent.

    Pass allow_caution=True to extend automatic execution to reversible-state
    commands (still excludes destructive + unclassified)."""
    cls = classify_command(command)
    if cls == SafetyClass.SAFE:
        return True
    if cls == SafetyClass.CAUTION and allow_caution:
        return True
    return False
