"""exo plan — fleet rebalancing CLI."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from exo_runtime.plan import (
    load_fleet, balance_fleet, evaluate_placement, build_migration_plan,
    PlacementStrategy,
)
from exo_runtime.plan.render import write_plan
from exo_runtime.plan.balancer import _usable_ram

console = Console()


def run(*, fleet_path: str, strategy: str = "specialized",
        out_dir: str | None = None, steps_per_wave: int = 3) -> None:
    fleet = load_fleet(fleet_path)
    strat = PlacementStrategy(strategy)

    console.print(Panel.fit(
        f"[bold cyan]exo plan[/bold cyan] — fleet: [yellow]{fleet.name}[/yellow]\n"
        f"Strategy: [cyan]{strat.value}[/cyan]  ·  "
        f"Hosts: [cyan]{len(fleet.hosts)}[/cyan]  ·  "
        f"Workloads: [cyan]{len(fleet.workloads)}[/cyan]",
        border_style="cyan",
    ))

    if fleet.description:
        console.print(f"[dim]{fleet.description}[/dim]")

    # Show current state
    cur_table = Table(title="Current state", show_header=True)
    cur_table.add_column("Host"); cur_table.add_column("CPU"); cur_table.add_column("RAM")
    cur_table.add_column("GPU"); cur_table.add_column("Workloads")
    cur_table.add_column("RAM allocated", justify="right")
    cur_table.add_column("% of total", justify="right")
    for h in fleet.hosts:
        wl = fleet.workloads_on(h.name)
        ram_alloc = sum(w.ram_mb for w in wl)
        pct = ram_alloc * 100 // h.ram_mb if h.ram_mb else 0
        color = "red" if pct > 90 else "yellow" if pct > 75 else "green"
        cur_table.add_row(
            h.name, f"{h.cpu_threads} thr",
            f"{h.ram_mb} MB",
            "✓ " + h.gpu_model if h.has_gpu else "—",
            str(len(wl)),
            f"{ram_alloc} MB",
            f"[{color}]{pct}%[/{color}]",
        )
    console.print(cur_table)

    placement = balance_fleet(fleet, strategy=strat)
    metrics = evaluate_placement(placement, fleet)

    # Show target state
    tgt_table = Table(title="Target state (after rebalance)", show_header=True)
    tgt_table.add_column("Host"); tgt_table.add_column("Workloads")
    tgt_table.add_column("RAM used", justify="right")
    tgt_table.add_column("Usable RAM", justify="right")
    tgt_table.add_column("Utilization", justify="right")
    for h in fleet.hosts:
        ram_used = placement.host_ram_used.get(h.name, 0)
        count = placement.host_workload_count.get(h.name, 0)
        usable = _usable_ram(h)
        pct = ram_used * 100 // usable if usable else 0
        color = "red" if pct > 90 else "yellow" if pct > 75 else "green"
        tgt_table.add_row(
            h.name, str(count),
            f"{ram_used} MB", f"{usable} MB",
            f"[{color}]{pct}%[/{color}]",
        )
    console.print(tgt_table)

    console.print(f"\nUtilization variance: [cyan]{metrics['variance']}[/cyan] "
                  f"(min {metrics['util_min']}%, max {metrics['util_max']}%)")

    if placement.violations:
        console.print(f"\n[bold red]⚠ {len(placement.violations)} constraint violation(s):[/bold red]")
        for v in placement.violations:
            console.print(f"  - [yellow]{v.workload}[/yellow] → {v.target_host}: {v.reason}")

    migration = build_migration_plan(fleet, placement, steps_per_wave=steps_per_wave)
    moves = sum(len(w.steps) for w in migration.waves)

    if moves == 0:
        console.print("\n[bold green]No moves required — current placement is balanced.[/bold green]")
    else:
        console.print(f"\n[bold]Migration plan: {moves} moves in {len(migration.waves)} wave(s)[/bold]")
        for wave in migration.waves:
            console.print(f"\n  [cyan]Wave {wave.wave_n}[/cyan] · {wave.label} ({len(wave.steps)} moves)")
            for s in wave.steps:
                risk_color = "red" if s.risk_score >= 8 else "yellow" if s.risk_score >= 5 else "green"
                console.print(
                    f"    - [{risk_color}]risk {s.risk_score}/10[/{risk_color}]  "
                    f"{s.workload.name} ({s.workload.workload_id}): "
                    f"{s.from_host} → {s.to_host}"
                )

    # Persist
    if out_dir is None:
        out_dir = str(Path(fleet_path).parent / "exo-plan")
    out_path = write_plan(fleet, placement, migration, Path(out_dir))
    console.print(f"\n[dim]Plan written to: {out_path}[/dim]")
