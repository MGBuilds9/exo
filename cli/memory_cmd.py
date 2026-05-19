"""exo memory — inspect, annotate, and query the session memory store.

Subcommands:
  exo memory list                            — recent sessions
  exo memory stats                           — counts + calibration summary
  exo memory show <session-id>               — one session's details
  exo memory outcome <session-id> <issue>    — record what was actually wrong
  exo memory regret <issue> <what-you-tried> — record a negative result
  exo memory recall <signal>                 — show prior outcomes for a signal
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import click
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from exo_runtime.memory import MemoryStore

console = Console()


@click.group("memory", help="Inspect + annotate the exo session memory store.")
def memory() -> None:
    pass


@memory.command("list")
@click.option("--limit", default=20, help="How many sessions to show.")
def cmd_list(limit: int) -> None:
    """Recent sessions."""
    with MemoryStore() as s:
        rows = s.all_sessions(limit=limit)
    if not rows:
        console.print("[yellow]No sessions recorded yet. Run `exo execute` first.[/yellow]")
        return
    t = Table(show_header=True)
    t.add_column("session_id"); t.add_column("started"); t.add_column("resolution")
    t.add_column("steps", justify="right"); t.add_column("plan")
    for r in rows:
        t.add_row(
            r["session_id"], r["started_at"][:19], r["resolution"],
            str(r["step_count"]), Path(r["plan_source"]).name,
        )
    console.print(t)


@memory.command("stats")
def cmd_stats() -> None:
    """Counts + calibration summary."""
    with MemoryStore() as s:
        n_sessions = s.session_count()
        n_outcomes = s.outcome_count()
        n_negative = int(s.conn.execute(
            "SELECT COUNT(*) FROM negative_results").fetchone()[0])
        n_signals = int(s.conn.execute(
            "SELECT COUNT(DISTINCT signal) FROM observed_signals").fetchone()[0])
    console.print(f"[bold]Memory store[/bold] at [cyan]{MemoryStore().path}[/cyan]")
    console.print(f"  Sessions:         {n_sessions}")
    console.print(f"  Outcomes:         {n_outcomes}")
    console.print(f"  Negative results: {n_negative}")
    console.print(f"  Distinct signals: {n_signals}")
    if n_sessions > 0 and n_outcomes == 0:
        console.print(
            "\n[yellow]No outcomes recorded yet — calibration unavailable.[/yellow]\n"
            "  Record one with: [cyan]exo memory outcome <session-id> <issue-name>[/cyan]"
        )


@memory.command("show")
@click.argument("session_id")
def cmd_show(session_id: str) -> None:
    """One session's full details."""
    with MemoryStore() as s:
        row = s.conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,),
        ).fetchone()
        if not row:
            console.print(f"[red]No session with id: {session_id}[/red]")
            sys.exit(2)
        console.print(f"[bold]{session_id}[/bold] — {row['resolution']}")
        console.print(f"  Plan:    {row['plan_source']}")
        console.print(f"  Started: {row['started_at']}")
        console.print(f"  Ended:   {row['ended_at']}")
        console.print(f"  Steps:   {row['step_count']}")

        steps = s.conn.execute(
            "SELECT * FROM steps WHERE session_id = ? ORDER BY step_n",
            (session_id,),
        ).fetchall()
        for step in steps:
            console.print(f"\n  [bold]Step {step['step_n']}[/bold] · {step['issue_name']}")
            console.print(f"    {step['proposed_command']}")
            console.print(f"    safety={step['safety_class']}  decision={step['user_decision']}  exit={step['exit_code']}")
            sigs = s.conn.execute(
                "SELECT signal, severity, detail FROM observed_signals WHERE step_id = ?",
                (step["step_id"],),
            ).fetchall()
            for sig in sigs:
                console.print(f"      [dim]{sig['signal']}({sig['severity']}): {sig['detail']}[/dim]")


@memory.command("outcome")
@click.argument("session_id")
@click.argument("issue_name")
@click.option("--root-cause", default=None, help="What actually was wrong.")
@click.option("--component-type", default=None)
@click.option("--correct-hypothesis", type=int, default=None,
              help="Which hypothesis index (0-based) was right, if any.")
@click.option("--fix", default=None, help="What fix was applied.")
def cmd_outcome(session_id: str, issue_name: str,
                root_cause: str | None, component_type: str | None,
                correct_hypothesis: int | None, fix: str | None) -> None:
    """Record what was actually wrong for an issue in a past session."""
    if not root_cause:
        root_cause = Prompt.ask("What was the actual root cause?")
    if not fix:
        fix = Prompt.ask("What fix was applied? (or 'unfixed')", default="unfixed")
    with MemoryStore() as s:
        oid = s.record_outcome(
            session_id=session_id,
            issue_name=issue_name,
            confirmed_root_cause=root_cause,
            component_type=component_type,
            correct_hypothesis_index=correct_hypothesis,
            fix_applied=fix,
        )
    console.print(f"[green]Recorded outcome #{oid}[/green]")


@memory.command("regret")
@click.argument("issue_name")
@click.argument("what_was_tried")
@click.option("--why", default=None, help="Why it didn't work.")
@click.option("--component-type", default=None)
@click.option("--signal", "signals", multiple=True,
              help="Top observed signal(s) at the time, repeatable.")
def cmd_regret(issue_name: str, what_was_tried: str, why: str | None,
               component_type: str | None, signals: tuple[str, ...]) -> None:
    """Record a negative result — something we tried that didn't fix it."""
    if not why:
        why = Prompt.ask("Why didn't it work? (one-liner)", default="(no detail)")
    with MemoryStore() as s:
        rid = s.record_negative_result(
            issue_name=issue_name,
            what_was_tried=what_was_tried,
            why_it_didnt_work=why,
            component_type=component_type,
            top_signals=list(signals),
        )
    console.print(f"[green]Recorded negative result #{rid}[/green]")


@memory.command("recall")
@click.argument("signal")
@click.option("--limit", default=10)
def cmd_recall(signal: str, limit: int) -> None:
    """Show prior outcomes for a given observed signal."""
    with MemoryStore() as s:
        rows = s.prior_outcomes_for_signal(signal, limit=limit)
    if not rows:
        console.print(f"[yellow]No prior outcomes recorded for signal `{signal}`.[/yellow]")
        return
    console.print(f"[bold]Prior outcomes for `{signal}`[/bold]:")
    for r in rows:
        console.print(f"  · [cyan]{r['issue_name']}[/cyan] ({r['component_type'] or '—'})")
        console.print(f"    Root cause: {r['confirmed_root_cause']}")
        if r["fix_applied"]:
            console.print(f"    Fix:        [dim]{r['fix_applied']}[/dim]")
        console.print(f"    [dim]{r['recorded_at'][:19]}[/dim]")


def run() -> None:
    """Entry point used by the top-level click registration."""
    memory()
