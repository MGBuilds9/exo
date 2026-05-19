"""Parse command output into observed signals.

Heuristic-based, rule-driven. For each known diagnostic command we have a
parser that extracts the meaningful signals. Unknown commands are passed
through as raw observations.

The point: turn a wall of text from `pvesm status` into structured data
the next decision step can use — "storage 'local-zfs' is inactive" — not
just "here's 500 lines, figure it out yourself."
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ObservedSignal:
    """One actionable observation from command output."""
    signal: str               # short tag, e.g. "storage_inactive"
    severity: int             # 0-10
    detail: str               # human-readable detail
    raw_excerpt: Optional[str] = None
    evidence_keys: list[str] = field(default_factory=list)


# === Parser dispatchers ======================================================

def parse_pvesm_status(stdout: str) -> list[ObservedSignal]:
    signals = []
    # Expected lines look like: "local-zfs        zfspool   active   ..."
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("Name") or line.startswith("-"):
            continue
        parts = re.split(r"\s+", line)
        if len(parts) < 3:
            continue
        name, kind, active = parts[0], parts[1], parts[2]
        if active.lower() in ("inactive", "disabled", "off"):
            signals.append(ObservedSignal(
                signal="storage_inactive",
                severity=8,
                detail=f"Storage '{name}' ({kind}) is {active.lower()}",
                raw_excerpt=line,
            ))
        elif "warn" in active.lower() or "degrad" in active.lower():
            signals.append(ObservedSignal(
                signal="storage_degraded",
                severity=6,
                detail=f"Storage '{name}' ({kind}) is {active.lower()}",
                raw_excerpt=line,
            ))
    if not signals:
        signals.append(ObservedSignal(
            signal="storage_healthy",
            severity=0,
            detail="All declared storages report active",
        ))
    return signals


def parse_df(stdout: str) -> list[ObservedSignal]:
    signals = []
    # df -h: Filesystem ... Size Used Avail Use% Mounted on
    for line in stdout.splitlines():
        line = line.strip()
        m = re.search(r"(\d+)%\s+(\S+)$", line)
        if not m:
            continue
        try:
            pct = int(m.group(1))
        except ValueError:
            continue
        mount = m.group(2)
        if pct >= 95:
            signals.append(ObservedSignal(signal="disk_critical", severity=9,
                                          detail=f"{mount} at {pct}% — critical",
                                          raw_excerpt=line))
        elif pct >= 85:
            signals.append(ObservedSignal(signal="disk_high", severity=6,
                                          detail=f"{mount} at {pct}% — watch",
                                          raw_excerpt=line))
    if not signals:
        signals.append(ObservedSignal(signal="disk_healthy", severity=0,
                                      detail="All filesystems below 85% used"))
    return signals


def parse_free(stdout: str) -> list[ObservedSignal]:
    signals = []
    swap_used_pct = None
    mem_avail_pct = None
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("Mem:"):
            parts = re.split(r"\s+", line)
            if len(parts) >= 7:
                try:
                    total = float(parts[1]); used = float(parts[2]); avail = float(parts[6])
                    if total > 0:
                        mem_avail_pct = round(avail / total * 100, 1)
                except (ValueError, IndexError):
                    pass
        elif line.startswith("Swap:"):
            parts = re.split(r"\s+", line)
            if len(parts) >= 3:
                try:
                    total = float(parts[1]); used = float(parts[2])
                    if total > 0:
                        swap_used_pct = round(used / total * 100, 1)
                except (ValueError, IndexError):
                    pass

    if swap_used_pct is not None:
        if swap_used_pct >= 70:
            signals.append(ObservedSignal(signal="swap_pressure", severity=7,
                                          detail=f"Swap at {swap_used_pct}% — memory pressure"))
        elif swap_used_pct >= 40:
            signals.append(ObservedSignal(signal="swap_moderate", severity=4,
                                          detail=f"Swap at {swap_used_pct}%"))
    if mem_avail_pct is not None and mem_avail_pct < 10:
        signals.append(ObservedSignal(signal="memory_low", severity=8,
                                      detail=f"Only {mem_avail_pct}% RAM available"))
    if not signals:
        signals.append(ObservedSignal(signal="memory_healthy", severity=0,
                                      detail="Memory and swap within healthy ranges"))
    return signals


def parse_systemctl_failed(stdout: str) -> list[ObservedSignal]:
    failed = [line for line in stdout.splitlines() if "failed" in line.lower() and not line.lower().startswith("legend")]
    # systemctl --failed prints a header "0 loaded units listed" when nothing is failed
    # We look for entries — typical format: "● unit-name.service ..."
    units = [l for l in failed if l.strip().startswith("●") or ".service" in l or ".timer" in l]
    if units:
        return [ObservedSignal(
            signal="failed_units",
            severity=7,
            detail=f"{len(units)} failed systemd unit(s): "
                   + ", ".join(u.strip().split()[1] for u in units[:5] if len(u.strip().split()) > 1),
        )]
    return [ObservedSignal(signal="systemd_healthy", severity=0,
                           detail="No failed systemd units")]


def parse_mount_nfs(stdout: str) -> list[ObservedSignal]:
    signals = []
    for line in stdout.splitlines():
        if "nfs" not in line.lower():
            continue
        if "stale" in line.lower() or "unreachable" in line.lower():
            signals.append(ObservedSignal(signal="nfs_stale", severity=8,
                                          detail=line.strip()[:200]))
    if not signals and "nfs" in stdout.lower():
        signals.append(ObservedSignal(signal="nfs_present", severity=0,
                                      detail=f"{stdout.lower().count('nfs')} nfs mounts found, none flagged"))
    return signals


def parse_zpool_status(stdout: str) -> list[ObservedSignal]:
    signals = []
    if "state: DEGRADED" in stdout or "state: FAULTED" in stdout:
        m = re.search(r"^\s*pool:\s+(\S+)", stdout, re.MULTILINE)
        pool = m.group(1) if m else "unknown"
        signals.append(ObservedSignal(signal="zpool_degraded", severity=9,
                                      detail=f"ZFS pool '{pool}' is not ONLINE"))
    if "errors: No known data errors" in stdout:
        if not signals:
            signals.append(ObservedSignal(signal="zpool_healthy", severity=0,
                                          detail="All pools ONLINE, no data errors"))
    return signals or [ObservedSignal(signal="zpool_unknown", severity=2,
                                       detail="Output did not match expected zpool patterns")]


# Dispatch table — match command prefix to parser
PARSER_DISPATCH = [
    (re.compile(r"^\s*(ssh\s+\S+\s+['\"])?pvesm\s+status"), parse_pvesm_status),
    (re.compile(r"^\s*(ssh\s+\S+\s+['\"])?df\b"), parse_df),
    (re.compile(r"^\s*(ssh\s+\S+\s+['\"])?free\b"), parse_free),
    (re.compile(r"^\s*(ssh\s+\S+\s+['\"])?systemctl\s+--failed"), parse_systemctl_failed),
    (re.compile(r"^\s*(ssh\s+\S+\s+['\"])?mount\b"), parse_mount_nfs),
    (re.compile(r"^\s*(ssh\s+\S+\s+['\"])?zpool\s+status"), parse_zpool_status),
]


def parse_output(command: str, stdout: str, stderr: str = "",
                 exit_code: int = 0) -> list[ObservedSignal]:
    """Parse command output into observed signals.

    Combines stdout + stderr for inspection; some Linux tools emit
    diagnostics on stderr.
    """
    text = stdout + ("\n" + stderr if stderr else "")
    if exit_code != 0 and not text.strip():
        return [ObservedSignal(
            signal="command_failed",
            severity=5,
            detail=f"Command exited {exit_code} with no output — investigate why",
        )]

    cmd = command.strip()
    for regex, parser in PARSER_DISPATCH:
        if regex.search(cmd):
            return parser(text)

    # No specific parser — return raw observation
    return [ObservedSignal(
        signal="raw_output",
        severity=3,
        detail=f"No structured parser for this command; raw output captured ({len(text)} chars)",
        raw_excerpt=text[:500],
    )]
