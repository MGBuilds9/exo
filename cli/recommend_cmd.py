"""exo recommend — data-driven repo scorer CLI."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from exo_runtime.recommend import (
    score_candidates, get_capability, list_capabilities,
    score_as_dict,
)

console = Console()


def list_capabilities_cmd() -> None:
    caps = list_capabilities()
    table = Table(title="exo recommend — available capabilities",
                  show_header=True, header_style="bold cyan")
    table.add_column("Slug", style="cyan")
    table.add_column("Description")
    table.add_column("Candidates", justify="right")
    for c in caps:
        table.add_row(c["slug"], c["description"], str(len(c["candidate_pool"])))
    console.print(table)


def run(*, capability: str, license_constraint: str = "any",
        weight_profile: str = "default", as_json: bool = False,
        out_dir: str | None = None) -> None:
    if capability == "list":
        list_capabilities_cmd()
        return

    cap = get_capability(capability)
    if cap is None:
        console.print(f"[red]No such capability: {capability}[/red]")
        console.print("Run [bold]exo recommend list[/bold] to see available capabilities.")
        sys.exit(2)

    candidates = cap["candidate_pool"]
    if not as_json:
        console.print(Panel.fit(
            f"[bold cyan]exo recommend[/bold cyan] · capability: [yellow]{capability}[/yellow]\n"
            f"{cap['description']}\n"
            f"[dim]Scoring {len(candidates)} candidates against live GitHub data...[/dim]\n"
            f"[dim]license-constraint: {license_constraint}  ·  weight-profile: {weight_profile}[/dim]",
            border_style="cyan",
        ))

    scored = score_candidates(candidates,
                              license_constraint=license_constraint,
                              weight_profile=weight_profile,
                              verbose=not as_json)

    # Build report
    report = {
        "capability": capability,
        "capability_description": cap["description"],
        "license_constraint": license_constraint,
        "weight_profile": weight_profile,
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "candidates_evaluated": len(scored),
        "ranking": [score_as_dict(s) for s in scored],
    }

    if as_json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _render(scored, cap)

    if out_dir:
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        file_name = f"{capability}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        (out_path / file_name).write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        if not as_json:
            console.print(f"\n[dim]Snapshot saved → {out_path / file_name}[/dim]")


def _render(scored: list, cap: dict) -> None:
    table = Table(title=f"Ranked candidates for: {cap['slug']}",
                  show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=3)
    table.add_column("Repo", style="cyan")
    table.add_column("Score", justify="right", style="bold")
    table.add_column("★", justify="right", style="yellow")
    table.add_column("Push", justify="center")
    table.add_column("Contribs", justify="right")
    table.add_column("90d cmts", justify="right")
    table.add_column("License")
    for i, s in enumerate(scored, 1):
        sig = s.signals
        push_label = "—"
        if sig.pushed_at:
            from datetime import datetime as _dt, timezone as _tz
            try:
                dt = _dt.fromisoformat(sig.pushed_at.replace("Z", "+00:00"))
                days = (_dt.now(_tz.utc) - dt).days
                if days < 7: push_label = f"[green]{days}d[/green]"
                elif days < 30: push_label = f"[yellow]{days}d[/yellow]"
                elif days < 180: push_label = f"[orange]{days}d[/orange]"
                else: push_label = f"[red]{days}d[/red]"
            except Exception:
                push_label = "?"
        if sig.fetch_error:
            table.add_row(str(i), s.full_name, "[red]FAIL[/red]",
                          "—", "—", "—", "—", "—")
            continue
        composite_color = "green" if s.composite >= 7 else "yellow" if s.composite >= 5 else "red"
        table.add_row(
            str(i), s.full_name,
            f"[{composite_color}]{s.composite}[/{composite_color}]",
            str(sig.stars),
            push_label,
            str(sig.contributor_count),
            str(sig.recent_commit_count_90d),
            sig.license_key or "[red]none[/red]",
        )
    console.print(table)

    # Sub-score breakdown for top 3
    if scored:
        console.print("\n[bold]Top 3 — sub-score breakdown:[/bold]")
        for i, s in enumerate(scored[:3], 1):
            console.print(
                f"\n[bold cyan]{i}. {s.full_name}[/bold cyan]  "
                f"maintenance=[bold]{s.maintenance}[/bold] · "
                f"popularity=[bold]{s.popularity}[/bold] · "
                f"governance=[bold]{s.governance}[/bold] · "
                f"license_fit=[bold]{s.license_fit}[/bold] → "
                f"composite=[bold]{s.composite}[/bold]"
            )
            for r in s.rationale[:5]:
                console.print(f"    [dim]{r}[/dim]")
            if len(s.rationale) > 5:
                console.print(f"    [dim]... +{len(s.rationale) - 5} more signals[/dim]")

    if cap.get("notes"):
        console.print(f"\n[italic dim]{cap['notes']}[/italic dim]")
