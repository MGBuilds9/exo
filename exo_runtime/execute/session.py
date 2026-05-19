"""Track a multi-step execute session — state, transcript, and the
"what should we do next" decision.

The session is the closing-the-loop artifact. Each step records:
- The command we asked the user to consent to
- Whether they approved
- The command result
- The parsed signals
- The next step we chose (or "stop / escalate / resolved")

Session is written to a markdown file as it progresses, so even if the
process crashes mid-loop, the user has a paper trail.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class SessionStep:
    """One step of an execute session."""
    step_n: int
    timestamp: str
    issue_name: str
    proposed_command: str
    safety_class: str
    user_decision: str           # approved / skipped / aborted / auto-ran
    command_result: Optional[dict] = None  # CommandResult.__dict__-ish
    observed_signals: list[dict] = field(default_factory=list)
    next_step_decision: str = ""
    next_step_command: Optional[str] = None
    notes: str = ""


@dataclass
class ExecuteSession:
    """A single execute session."""
    session_id: str
    plan_source: str
    started_at: str
    ended_at: Optional[str] = None
    steps: list[SessionStep] = field(default_factory=list)
    resolution: str = "in_progress"   # in_progress / resolved / escalated / aborted
    summary: str = ""


def new_session(plan_source: str) -> ExecuteSession:
    sid = datetime.now().strftime("exec-%Y%m%d-%H%M%S")
    return ExecuteSession(
        session_id=sid,
        plan_source=plan_source,
        started_at=datetime.now(timezone.utc).isoformat(),
    )


def append_step(session: ExecuteSession, step: SessionStep) -> None:
    session.steps.append(step)


def finalize(session: ExecuteSession, resolution: str, summary: str) -> None:
    session.ended_at = datetime.now(timezone.utc).isoformat()
    session.resolution = resolution
    session.summary = summary


def write_session_md(session: ExecuteSession, out_path: Path) -> None:
    """Render the session as markdown."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# exo execute session — {session.session_id}",
        "",
        f"- **Plan source:** `{session.plan_source}`",
        f"- **Started:** {session.started_at}",
        f"- **Ended:** {session.ended_at or '(in progress)'}",
        f"- **Resolution:** **{session.resolution}**",
        f"- **Steps:** {len(session.steps)}",
        "",
    ]
    if session.summary:
        lines.append("## Summary")
        lines.append("")
        lines.append(session.summary)
        lines.append("")

    lines.append("## Step-by-step transcript")
    lines.append("")
    for step in session.steps:
        lines.append(f"### Step {step.step_n} · {step.issue_name}")
        lines.append("")
        lines.append(f"- **Timestamp:** {step.timestamp}")
        lines.append(f"- **Proposed command** (safety: `{step.safety_class}`):")
        lines.append("  ```")
        lines.append(f"  {step.proposed_command}")
        lines.append("  ```")
        lines.append(f"- **User decision:** {step.user_decision}")
        if step.command_result:
            r = step.command_result
            lines.append(f"- **Exit code:** {r.get('exit_code')}")
            lines.append(f"- **Elapsed:** {r.get('elapsed_seconds', '?')}s")
            if r.get("stdout"):
                lines.append("- **Stdout** (first 50 lines):")
                lines.append("  ```")
                for ln in r["stdout"].split("\n")[:50]:
                    lines.append(f"  {ln}")
                lines.append("  ```")
            if r.get("stderr"):
                stderr_lines = r["stderr"].split("\n")
                if any(l.strip() for l in stderr_lines):
                    lines.append("- **Stderr** (first 20 lines):")
                    lines.append("  ```")
                    for ln in stderr_lines[:20]:
                        lines.append(f"  {ln}")
                    lines.append("  ```")
        if step.observed_signals:
            lines.append("- **Observed signals:**")
            for sig in step.observed_signals:
                sev = sig.get("severity", 0)
                marker = "🔴" if sev >= 7 else ("🟡" if sev >= 4 else "🟢")
                lines.append(f"  - {marker} `{sig.get('signal','?')}` (sev {sev}): {sig.get('detail','')}")
        if step.next_step_decision:
            lines.append(f"- **Next step decision:** {step.next_step_decision}")
        if step.next_step_command:
            lines.append("  ```")
            lines.append(f"  {step.next_step_command}")
            lines.append("  ```")
        if step.notes:
            lines.append(f"- **Notes:** {step.notes}")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_session_json(session: ExecuteSession, out_path: Path) -> None:
    """Render the session as JSON (for downstream tools)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(asdict(session), indent=2, default=str), encoding="utf-8")
