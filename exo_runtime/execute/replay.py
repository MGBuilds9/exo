"""Replay runner — return synthetic CommandResults from a YAML fixture.

Lets the planner+parser+next-step chain be tested end-to-end without
touching real infrastructure. Used by --replay flag on `exo execute`
and by CI tests in tests/fixtures/execute-replays/.

Fixture format:

  description: short human label
  responses:
    - command_regex: "^pvesm status"   # regex matched against the command
      stdout: |
        ...synthetic stdout...
      stderr: ""
      exit_code: 0
      elapsed_seconds: 0.5
    - command_regex: ...
      ...

The first regex that matches the proposed command wins. If nothing
matches, the replay runner returns exit_code=127 with a "not found in
fixture" stderr — making misses loud.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from .runner import CommandResult


@dataclass
class ReplayResponse:
    command_regex: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    elapsed_seconds: float = 0.1
    times_matched: int = 0   # mutated as we replay


@dataclass
class ReplayFixture:
    description: str
    responses: list[ReplayResponse] = field(default_factory=list)
    path: Optional[Path] = None

    def find(self, command: str) -> Optional[ReplayResponse]:
        for r in self.responses:
            if re.search(r.command_regex, command):
                return r
        return None

    def unused(self) -> list[ReplayResponse]:
        return [r for r in self.responses if r.times_matched == 0]


def load_fixture(path: Path | str) -> ReplayFixture:
    p = Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    responses = [ReplayResponse(
        command_regex=r["command_regex"],
        stdout=r.get("stdout", ""),
        stderr=r.get("stderr", ""),
        exit_code=int(r.get("exit_code", 0)),
        elapsed_seconds=float(r.get("elapsed_seconds", 0.1)),
    ) for r in raw.get("responses", [])]
    return ReplayFixture(
        description=raw.get("description", p.stem),
        responses=responses,
        path=p,
    )


class ReplayRunner:
    """Drop-in replacement for runner.run_command — but reads from a fixture."""

    def __init__(self, fixture: ReplayFixture):
        self.fixture = fixture

    def __call__(self, command: str, timeout: int = 60,
                 cwd: Optional[str] = None, shell: bool = True) -> CommandResult:
        started_at = datetime.now(timezone.utc).isoformat()
        match = self.fixture.find(command)
        if not match:
            return CommandResult(
                command=command, exit_code=127, stdout="",
                stderr=f"[replay] no fixture response matched command: {command}",
                elapsed_seconds=0.0, timed_out=False, started_at=started_at,
            )
        match.times_matched += 1
        return CommandResult(
            command=command,
            exit_code=match.exit_code,
            stdout=match.stdout,
            stderr=match.stderr,
            elapsed_seconds=match.elapsed_seconds,
            timed_out=False,
            started_at=started_at,
        )
