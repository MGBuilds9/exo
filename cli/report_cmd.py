"""exo report — pretty-print a completed run's summary + transcript head."""
from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()


def run(*, run_dir: str) -> None:
    run_path = Path(run_dir)
    summary_path = run_path / "summary.md"
    transcript_path = run_path / "transcript.jsonl"

    if not summary_path.exists():
        console.print(f"[red]No summary.md in {run_path}[/red]")
        return

    summary = summary_path.read_text(encoding="utf-8")
    console.print(Panel(Syntax(summary, "markdown"), title="summary.md", border_style="cyan"))

    if transcript_path.exists():
        lines = transcript_path.read_text(encoding="utf-8").splitlines()
        console.print(f"\n[bold]Transcript: {len(lines)} turns[/bold]")
        console.print(f"  File: [cyan]{transcript_path}[/cyan]")
        console.print(f"  First 3 turns:")
        for line in lines[:3]:
            try:
                obj = json.loads(line)
                console.print(f"    [dim]T{obj.get('turn'):>2}[/dim] [{obj.get('actor_id')}]: {obj.get('content','')[:120]}")
            except json.JSONDecodeError:
                pass
