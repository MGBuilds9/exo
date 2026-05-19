"""Run a command with capture, timeout, and explicit working-directory awareness.

Returns a CommandResult — exit code, stdout, stderr, elapsed seconds, and
whether the timeout fired. Does NOT do any safety classification —
that's safety.py's job; the runner is dumb on purpose.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    timed_out: bool = False
    started_at: str = ""

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    @property
    def combined_output(self) -> str:
        parts = [self.stdout.rstrip()] if self.stdout.strip() else []
        if self.stderr.strip():
            parts.append(f"--- stderr ---\n{self.stderr.rstrip()}")
        return "\n".join(parts)


def run_command(command: str, timeout: int = 60,
                cwd: Optional[str] = None,
                shell: bool = True) -> CommandResult:
    """Run command, capture stdout/stderr, return CommandResult.

    Uses shell=True so users can pipe and use shell builtins; safety.py
    is responsible for ensuring only sane commands reach here.
    """
    from datetime import datetime, timezone
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.time()
    try:
        proc = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            encoding="utf-8",
            errors="replace",
        )
        elapsed = time.time() - t0
        return CommandResult(
            command=command,
            exit_code=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            elapsed_seconds=round(elapsed, 2),
            timed_out=False,
            started_at=started_at,
        )
    except subprocess.TimeoutExpired as e:
        elapsed = time.time() - t0
        return CommandResult(
            command=command,
            exit_code=-1,
            stdout=(e.stdout.decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")),
            stderr=(e.stderr.decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")) + f"\n[TIMEOUT after {timeout}s]",
            elapsed_seconds=round(elapsed, 2),
            timed_out=True,
            started_at=started_at,
        )
