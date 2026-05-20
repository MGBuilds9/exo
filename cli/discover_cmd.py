"""exo discover — auto-build fleet.yaml from live infrastructure.

Single command. Probes a Proxmox seed host via SSH to enumerate the
cluster, sweeps the LAN for unmanaged devices, cross-references the
existing HOMELAB-INVENTORY.md, classifies unmanaged devices into tiers,
and writes a fleet.yaml ready for `exo plan`.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from exo_runtime.discover import (
    probe_proxmox_cluster, probe_lan_subnet, read_inventory,
    classify_unmanaged, synthesize_fleet, DiscoveryResult,
)
from exo_runtime.discover.synth import fleet_to_yaml, unmanaged_report

console = Console()


def run(*, proxmox_hosts: list[str], subnet: str, inventory_path: str | None,
        out_path: str, fleet_name: str, ssh_user: str = "root",
        skip_lan: bool = False, verbose: bool = False) -> None:
    console.print(Panel.fit(
        f"[bold cyan]exo discover[/bold cyan]\n"
        f"Proxmox seeds: [yellow]{', '.join(proxmox_hosts)}[/yellow]\n"
        f"LAN subnet:    [yellow]{subnet}[/yellow]"
        + (" [dim](skipped)[/dim]" if skip_lan else "")
        + f"\nInventory:     [yellow]{inventory_path or '(none)'}[/yellow]\n"
        f"Output:        [cyan]{out_path}[/cyan]",
        border_style="cyan",
    ))

    # 1. Proxmox cluster
    console.print("\n[bold]Probing Proxmox cluster via SSH...[/bold]")
    hosts, workloads = probe_proxmox_cluster(proxmox_hosts, ssh_user=ssh_user, verbose=verbose)
    if not hosts:
        console.print("[red]No Proxmox hosts discovered. Check SSH access to the seed IP(s).[/red]")
        sys.exit(2)
    console.print(f"[green]✓[/green] {len(hosts)} hosts, {len(workloads)} workloads")
    if verbose:
        for h in hosts:
            console.print(f"    [dim]{h.name} @ {h.ip} — {h.cpu_threads} thr / {h.ram_mb} MB"
                          + (f" / GPU {h.gpu_model}" if h.has_gpu else "") + "[/dim]")

    # 2. Inventory
    inv: dict = {}
    if inventory_path:
        inv = read_inventory(inventory_path)
        console.print(f"[green]✓[/green] {len(inv)} inventory entries from {inventory_path}")

    # 3. LAN sweep
    lan_devices: list = []
    classified: list = []
    if not skip_lan:
        console.print(f"\n[bold]Sweeping LAN {subnet}...[/bold]")
        lan_devices = probe_lan_subnet(subnet, verbose=verbose)
        console.print(f"[green]✓[/green] {len(lan_devices)} live devices on {subnet}")

        inventory_ips = {e.ip for e in inv.values()}
        managed_ips = {h.ip for h in hosts} | {w.current_host for w in workloads if w.current_host.count(".") == 3}
        # NPM routed IPs — we can detect courtesy ports + hostname patterns
        npm_routed = {d.ip for d in lan_devices
                      if "truenas" in d.hostname.lower() or
                         "homeassistant" in d.hostname.lower()}
        classified = classify_unmanaged(lan_devices, inventory_ips, managed_ips, npm_routed)

    # 4. Build result + synthesize
    result = DiscoveryResult(
        fleet_name=fleet_name,
        proxmox_hosts=hosts,
        proxmox_workloads=workloads,
        inventory=inv,
        lan_devices=lan_devices,
        classified=classified,
    )
    fleet = synthesize_fleet(result)
    yaml_text = fleet_to_yaml(fleet)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml_text, encoding="utf-8")
    console.print(f"\n[green]✓[/green] fleet.yaml written to [cyan]{out_path}[/cyan]")

    # 5. Unmanaged report
    if classified:
        unmgr = unmanaged_report(result)
        if unmgr["unmanaged_total"] > 0:
            console.print(f"\n[bold yellow]⚠ {unmgr['unmanaged_total']} unmanaged devices on the LAN — review:[/bold yellow]")
            t = Table(show_header=True)
            t.add_column("Tier"); t.add_column("Count", justify="right")
            t.add_column("Sample IPs")
            for tier, items in unmgr["by_tier"].items():
                ips = ", ".join(i["ip"] for i in items[:5])
                if len(items) > 5:
                    ips += f" (+{len(items)-5} more)"
                t.add_row(tier, str(len(items)), ips)
            console.print(t)
            console.print("[dim]Promote any unmanaged device into the fleet by adding it to fleet.yaml manually.[/dim]")

    # 6. Suggest next step
    console.print(f"\n[bold]Next:[/bold] [cyan]exo plan {out_path}[/cyan]")
