"""Adapters that turn fleet + plan + memory data into a view model.

Keeps Jinja templates dumb. Anything computed (RAM percentages, host
status from utilization, ghost-placement positions) is done here, not
in templates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from exo_runtime.plan import (
    load_fleet, balance_fleet, evaluate_placement, build_migration_plan,
    PlacementStrategy, Fleet, Workload, Host,
)


@dataclass
class HostVM:
    name: str
    ip: str
    cpu_threads: int
    ram_mb: int
    has_gpu: bool
    gpu_model: str
    role_hint: str
    notes: str
    # Computed
    workloads: list[dict] = field(default_factory=list)
    ram_used_mb: int = 0
    ram_used_pct: int = 0
    cpu_used: int = 0
    cpu_used_pct: int = 0
    status: str = "green"           # green/yellow/red — derived from utilization
    proposed_workloads: list[dict] = field(default_factory=list)   # ghosts after plan
    proposed_ram_used_mb: int = 0
    proposed_ram_used_pct: int = 0


@dataclass
class WorkloadVM:
    name: str
    workload_id: str
    workload_type: str
    current_host: str
    proposed_host: Optional[str]
    ram_mb: int
    cpu_threads: int
    needs_gpu: bool
    tier: str
    pin_to_host: Optional[str]
    is_moving: bool = False


@dataclass
class FleetViewModel:
    name: str
    description: str
    hosts: list[HostVM] = field(default_factory=list)
    workloads: list[WorkloadVM] = field(default_factory=list)
    strategy: str = "specialized"
    variance_before: float = 0.0
    variance_after: float = 0.0
    moves: list[dict] = field(default_factory=list)
    waves: list[dict] = field(default_factory=list)
    violations: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    discovered_at: Optional[str] = None
    fleet_path: str = ""


def _status_from_pct(pct: int) -> str:
    if pct >= 85:
        return "red"
    if pct >= 70:
        return "yellow"
    return "green"


def build_view_model(fleet_path: str | Path,
                     strategy: str = "specialized") -> FleetViewModel:
    """Load a fleet, compute current + proposed placement, return view model."""
    fleet: Fleet = load_fleet(fleet_path)
    placement = balance_fleet(fleet, strategy=PlacementStrategy(strategy))
    metrics = evaluate_placement(placement, fleet)
    migration = build_migration_plan(fleet, placement)

    # Build host VMs
    host_vms: list[HostVM] = []
    for h in fleet.hosts:
        cur_wls = fleet.workloads_on(h.name)
        cur_ram = sum(w.ram_mb for w in cur_wls)
        cur_cpu = sum(w.cpu_threads for w in cur_wls)
        ram_pct = cur_ram * 100 // h.ram_mb if h.ram_mb else 0
        cpu_pct = cur_cpu * 100 // h.cpu_threads if h.cpu_threads else 0
        proposed_wls_names = [w_name for w_name, h_name
                              in placement.assignments.items()
                              if h_name == h.name]
        proposed_ram = placement.host_ram_used.get(h.name, 0)
        proposed_ram_pct = proposed_ram * 100 // h.ram_mb if h.ram_mb else 0
        host_vms.append(HostVM(
            name=h.name, ip="",
            cpu_threads=h.cpu_threads, ram_mb=h.ram_mb,
            has_gpu=h.has_gpu, gpu_model=h.gpu_model or "",
            role_hint=h.role_hint, notes=h.notes,
            workloads=[{
                "name": w.name,
                "id": w.workload_id,
                "type": w.workload_type,
                "ram_mb": w.ram_mb,
                "cpu_threads": w.cpu_threads,
                "tier": w.tier,
                "needs_gpu": w.needs_gpu,
                "pin": w.pin_to_host,
            } for w in cur_wls],
            ram_used_mb=cur_ram, ram_used_pct=ram_pct,
            cpu_used=cur_cpu, cpu_used_pct=cpu_pct,
            status=_status_from_pct(ram_pct),
            proposed_workloads=[{
                "name": n,
                "from": next((w.current_host for w in fleet.workloads if w.name == n), ""),
            } for n in proposed_wls_names if next((w.current_host for w in fleet.workloads if w.name == n), "") != h.name],
            proposed_ram_used_mb=proposed_ram,
            proposed_ram_used_pct=proposed_ram_pct,
        ))

    # Build workload VMs (just the moves + a flat list)
    move_set = {w.name for w, _, _ in placement.moves(fleet)}
    workload_vms: list[WorkloadVM] = []
    for w in fleet.workloads:
        proposed = placement.assignments.get(w.name)
        workload_vms.append(WorkloadVM(
            name=w.name, workload_id=w.workload_id,
            workload_type=w.workload_type,
            current_host=w.current_host, proposed_host=proposed,
            ram_mb=w.ram_mb, cpu_threads=w.cpu_threads,
            needs_gpu=w.needs_gpu, tier=w.tier,
            pin_to_host=w.pin_to_host,
            is_moving=w.name in move_set,
        ))

    moves = [{"workload": w.name, "from": frm, "to": to,
              "ram_mb": w.ram_mb, "tier": w.tier}
             for w, frm, to in placement.moves(fleet)]
    waves = []
    for wave in migration.waves:
        waves.append({
            "n": wave.wave_n,
            "label": wave.label,
            "steps": [{
                "workload": s.workload.name,
                "id": s.workload.workload_id,
                "from": s.from_host,
                "to": s.to_host,
                "risk": s.risk_score,
                "risk_reason": s.risk_reason,
                "strategy": s.strategy,
            } for s in wave.steps],
        })

    return FleetViewModel(
        name=fleet.name,
        description=fleet.description or "",
        hosts=host_vms,
        workloads=workload_vms,
        strategy=strategy,
        variance_before=0.0,    # TODO: pre-balance variance
        variance_after=metrics.get("variance", 0.0),
        moves=moves,
        waves=waves,
        violations=[{"workload": v.workload, "target": v.target_host, "reason": v.reason}
                    for v in placement.violations],
        metrics=metrics,
        fleet_path=str(fleet_path),
    )
