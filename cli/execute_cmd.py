"""exo execute — run a solve plan with consent gates.

Reads a plan markdown (or re-runs solve internally). For each proposed
first-action, asks the user to approve / skip / abort. If approved, runs
the command, parses output into observed signals, and produces the next
recommended step (or closes the loop).

Safety:
- SAFE commands (read-only diagnostics) auto-runnable in `--auto` mode
- CAUTION commands always require explicit consent
- DESTRUCTIVE commands require double-confirmation even in --auto
- UNCLASSIFIED defaults to CAUTION (fail-cautious)
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from exo_runtime.execute import (
    classify_command, SafetyClass, run_command, parse_output,
    load_fixture, ReplayRunner,
)
from exo_runtime.execute.session import (
    new_session, append_step, finalize,
    write_session_md, write_session_json, SessionStep,
)
from exo_runtime.execute.runner import CommandResult
from exo_runtime.execute.parser import ObservedSignal
from exo_runtime.execute.safety import is_runnable_without_explicit_consent
from exo_runtime.memory import MemoryStore, tried_and_failed

console = Console()


def _safety_color(cls: SafetyClass) -> str:
    return {
        SafetyClass.SAFE: "green",
        SafetyClass.CAUTION: "yellow",
        SafetyClass.UNCLASSIFIED: "orange3",
        SafetyClass.DESTRUCTIVE: "red",
    }.get(cls, "white")


def _extract_actions_from_plan(plan_path: Path) -> list[dict]:
    """Parse a solve plan markdown into a list of executable actions.

    Each action: {issue_name, command, hypotheses (list), order}.
    """
    text = plan_path.read_text(encoding="utf-8")
    actions = []
    # Issue blocks start with `## <n>. <name> (...)`
    issue_pattern = re.compile(
        r"^##\s+\d+\.\s+(?P<name>[^\n(]+?)\s*\([^)]+\)\s*$",
        flags=re.MULTILINE,
    )
    cmd_pattern = re.compile(
        r"###\s+First action.*?\n.*?```\n(?P<cmd>.+?)\n```",
        flags=re.DOTALL,
    )
    hyp_pattern = re.compile(
        r"###\s+Hypotheses.*?\n(?P<block>(?:- .+\n)+)",
        flags=re.DOTALL,
    )

    issues = list(issue_pattern.finditer(text))
    for i, m in enumerate(issues):
        start = m.end()
        end = issues[i + 1].start() if i + 1 < len(issues) else len(text)
        block = text[start:end]
        cmd_m = cmd_pattern.search(block)
        hyp_m = hyp_pattern.search(block)
        if not cmd_m:
            continue
        hyps = []
        if hyp_m:
            for line in hyp_m.group("block").splitlines():
                line = line.strip()
                if line.startswith("-"):
                    hyps.append(line.lstrip("- ").strip())
        actions.append({
            "issue_name": m.group("name").strip(),
            "command": cmd_m.group("cmd").strip(),
            "hypotheses": hyps,
            "order": i + 1,
        })
    return actions


def _confirm(prompt_text: str, default: str = "skip",
             choices: tuple = ("run", "skip", "abort")) -> str:
    return Prompt.ask(prompt_text, choices=list(choices), default=default)


def _double_confirm_destructive(command: str) -> bool:
    console.print(
        f"\n[bold red]⚠ DESTRUCTIVE COMMAND DETECTED[/bold red]: "
        f"[yellow]{command}[/yellow]"
    )
    typed = Prompt.ask(
        "Type the literal phrase 'I understand the risk' to proceed, or anything else to skip",
        default="skip",
    )
    return typed.strip().lower() == "i understand the risk"


def _signals_to_dicts(signals: list[ObservedSignal]) -> list[dict]:
    return [
        {"signal": s.signal, "severity": s.severity, "detail": s.detail,
         "raw_excerpt": s.raw_excerpt, "evidence_keys": s.evidence_keys}
        for s in signals
    ]


def _propose_next_step(signals: list[ObservedSignal], hypotheses: list[str]) -> tuple[str, str]:
    """Given the signals we just observed, pick the next step's command (or
    return ("", "") to stop). Returns (next_command, decision_text)."""
    # If we saw a critical signal, suggest investigating it further
    crit = [s for s in signals if s.severity >= 8]
    if crit:
        primary = crit[0]
        # Map signal type to a follow-up command
        followup = _signal_to_followup(primary.signal)
        return (
            followup,
            f"Critical signal `{primary.signal}` ({primary.severity}) — propose follow-up to investigate"
            if followup else f"Critical signal `{primary.signal}` — surfacing as escalation",
        )

    mod = [s for s in signals if 4 <= s.severity < 8]
    if mod:
        primary = mod[0]
        followup = _signal_to_followup(primary.signal)
        return (
            followup,
            f"Moderate signal `{primary.signal}` — would normally investigate; user to confirm"
            if followup else f"Moderate signal `{primary.signal}` — escalating to user judgment",
        )

    # All clear
    return "", "No actionable signals — closing loop on this issue."


SIGNAL_FOLLOWUPS = {
    "storage_inactive": "pvesm set <storage-id> --disable 0  # (verify the storage is configured to be enabled; consult docs first)",
    "storage_degraded": "zpool status -v  # check the underlying pool",
    "disk_critical": "du -sh /* 2>/dev/null | sort -hr | head -10  # find what's eating space",
    "disk_high": "du -sh /var/log/* | sort -hr | head -5  # check log dirs first",
    "memory_low": "ps aux --sort=-rss | head -10  # find memory hogs",
    "swap_pressure": "ps aux --sort=-rss | head -10  # find what's swapping out",
    "failed_units": "journalctl -u <unit-name> -n 50 --no-pager  # check logs for failed unit",
    "nfs_stale": "umount -f -l <stale-mount>  # force-lazy-unmount the stale NFS share (CAUTION)",
    "zpool_degraded": "zpool status -v <pool>  # detailed status to find the failed device",
    "command_failed": "# investigate why the diagnostic command itself failed — permissions? path?",
}


def _signal_to_followup(signal: str) -> str:
    return SIGNAL_FOLLOWUPS.get(signal, "")


def run(*, plan_path: str, out_dir: str | None = None,
        auto: bool = False, allow_caution: bool = False,
        max_steps: int = 10,
        replay_fixture: str | None = None) -> None:
    p_in = Path(plan_path)
    if not p_in.exists():
        console.print(f"[red]Plan not found: {plan_path}[/red]")
        sys.exit(2)

    actions = _extract_actions_from_plan(p_in)
    if not actions:
        console.print("[yellow]No actionable steps found in the plan.[/yellow]")
        return

    # Pick command-runner: replay if a fixture is given, otherwise live subprocess.
    runner_fn = run_command
    replay_label = ""
    if replay_fixture:
        fixture = load_fixture(replay_fixture)
        runner_fn = ReplayRunner(fixture)
        replay_label = f"\n[bold magenta]REPLAY MODE[/bold magenta]: {fixture.description} ({Path(replay_fixture).name})"

    console.print(Panel.fit(
        f"[bold cyan]exo execute[/bold cyan] · plan: [yellow]{p_in.name}[/yellow]\n"
        f"Found {len(actions)} issue(s) with proposed first actions.\n"
        f"Mode: [cyan]{'auto (safe commands only)' if auto else 'interactive (confirm each step)'}[/cyan]  "
        f"max_steps: [cyan]{max_steps}[/cyan]{replay_label}",
        border_style="magenta" if replay_fixture else "cyan",
    ))

    session = new_session(str(p_in))
    step_n = 0

    for action in actions:
        if step_n >= max_steps:
            console.print("[yellow]Reached max_steps; pausing.[/yellow]")
            break
        step_n += 1

        cmd = action["command"]
        # If the planner's command is a template / placeholder, skip
        if "<id>" in cmd or "<unit-name>" in cmd or cmd.startswith("#"):
            console.print(f"\n[dim]Step {step_n}: {action['issue_name']} — proposed command is a template; needs manual fill. Skipping.[/dim]")
            console.print(f"  [yellow]{cmd}[/yellow]")
            step = SessionStep(
                step_n=step_n, timestamp=datetime.now(timezone.utc).isoformat(),
                issue_name=action["issue_name"],
                proposed_command=cmd, safety_class="template",
                user_decision="skipped_template",
                notes="Command contains placeholders; user must fill manually.",
            )
            append_step(session, step)
            continue

        cls = classify_command(cmd)
        color = _safety_color(cls)

        console.print(f"\n[bold]Step {step_n}/{min(len(actions), max_steps)}: {action['issue_name']}[/bold]")
        console.print(f"  [{color}]Safety: {cls.value}[/{color}]")
        console.print(f"  Command: [yellow]{cmd}[/yellow]")
        if action.get("hypotheses"):
            console.print("  Testing hypothesis (first-listed):")
            console.print(f"    [dim]{action['hypotheses'][0]}[/dim]")

        # Decision
        if cls == SafetyClass.DESTRUCTIVE:
            approved = _double_confirm_destructive(cmd)
            decision = "approved_destructive" if approved else "skipped_destructive"
        elif auto and is_runnable_without_explicit_consent(cmd, allow_caution=allow_caution):
            console.print("  [green]Auto-running (safe).[/green]")
            approved = True
            decision = "auto-ran"
        else:
            choice = _confirm(f"  Run, skip, or abort?", default="run", choices=("run", "skip", "abort"))
            if choice == "abort":
                finalize(session, "aborted", "User aborted at step {}.".format(step_n))
                break
            approved = (choice == "run")
            decision = {"run": "approved", "skip": "skipped"}[choice]

        # Execute (or not)
        result_dict = None
        signals = []
        next_cmd = ""
        next_decision = ""
        if approved:
            console.print("  [dim]Running...[/dim]")
            result = runner_fn(cmd, timeout=60)
            result_dict = {
                "command": result.command,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "elapsed_seconds": result.elapsed_seconds,
                "timed_out": result.timed_out,
            }
            console.print(f"  Exit: {result.exit_code}  Elapsed: {result.elapsed_seconds}s")
            if result.stdout.strip():
                preview = "\n".join(result.stdout.split("\n")[:10])
                console.print(f"  [dim]stdout (first 10 lines):[/dim]\n[dim]{preview}[/dim]")
            signals = parse_output(cmd, result.stdout, result.stderr, result.exit_code)
            for s in signals:
                marker = "🔴" if s.severity >= 7 else ("🟡" if s.severity >= 4 else "🟢")
                console.print(f"    {marker} [bold]{s.signal}[/bold] (sev {s.severity}): {s.detail}")

            next_cmd, next_decision = _propose_next_step(signals, action.get("hypotheses", []))
            if next_cmd:
                console.print(f"  [italic cyan]Next-step suggestion:[/italic cyan] {next_decision}")
                console.print(f"    [yellow]{next_cmd}[/yellow]")
            else:
                console.print(f"  [italic green]{next_decision}[/italic green]")

        step = SessionStep(
            step_n=step_n,
            timestamp=datetime.now(timezone.utc).isoformat(),
            issue_name=action["issue_name"],
            proposed_command=cmd,
            safety_class=cls.value,
            user_decision=decision,
            command_result=result_dict,
            observed_signals=_signals_to_dicts(signals),
            next_step_decision=next_decision,
            next_step_command=next_cmd or None,
        )
        append_step(session, step)

    if session.resolution == "in_progress":
        finalize(session, "completed",
                 f"Walked through {len(session.steps)} step(s) from the plan.")

    # Persist to disk artifacts
    if out_dir is None:
        out_dir = str(p_in.parent / "exo-execute")
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    md_path = out_path / f"{session.session_id}.md"
    json_path = out_path / f"{session.session_id}.json"
    write_session_md(session, md_path)
    write_session_json(session, json_path)

    # Persist to memory store (for recall, calibration, negative-results)
    try:
        from dataclasses import asdict
        with MemoryStore() as store:
            store.record_session(asdict(session))
        memory_status = "[green]session indexed to memory store[/green]"
    except Exception as e:
        memory_status = f"[yellow]memory store write failed: {e}[/yellow]"

    console.print(f"\n[bold green]Session complete — resolution: {session.resolution}[/bold green]")
    console.print(f"  Markdown: [cyan]{md_path}[/cyan]")
    console.print(f"  JSON:     [cyan]{json_path}[/cyan]")
    console.print(f"  Memory:   {memory_status}")
