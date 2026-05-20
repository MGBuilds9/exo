"""Compose discovery results into a fleet.yaml-compatible dict.

The output matches exo_runtime/plan/fleet.py's schema so `exo plan` can
consume it directly. A summary of unmanaged devices accompanies the
fleet for the user to review / label / promote into inventory.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import yaml

from .classify import ClassifiedDevice, DeviceTier
from .inventory import InventoryEntry
from .lan import LanDevice
from .proxmox import ProxmoxHost, ProxmoxWorkload


@dataclass
class DiscoveryResult:
    """Everything produced by a discover run."""
    fleet_name: str
    proxmox_hosts: list[ProxmoxHost] = field(default_factory=list)
    proxmox_workloads: list[ProxmoxWorkload] = field(default_factory=list)
    inventory: dict[str, InventoryEntry] = field(default_factory=dict)
    lan_devices: list[LanDevice] = field(default_factory=list)
    classified: list[ClassifiedDevice] = field(default_factory=list)
    discovered_at: str = ""

    def __post_init__(self):
        if not self.discovered_at:
            self.discovered_at = datetime.now(timezone.utc).isoformat()


def _host_role_hint(workloads_on_host: list[ProxmoxWorkload], has_gpu: bool) -> str:
    """Infer role hint from workload mix."""
    if has_gpu:
        return "compute"
    tiers = [w.tier for w in workloads_on_host]
    if tiers.count("storage") > len(tiers) / 3:
        return "storage"
    if tiers.count("edge") > len(tiers) / 3:
        return "edge"
    return "user"


def synthesize_fleet(result: DiscoveryResult) -> dict[str, Any]:
    """Build the fleet.yaml dict from a DiscoveryResult."""
    hosts_yaml = []
    for h in result.proxmox_hosts:
        wls = [w for w in result.proxmox_workloads if w.current_host == h.name]
        role = _host_role_hint(wls, h.has_gpu) or h.role_hint or "user"
        hosts_yaml.append({
            "name": h.name,
            "cpu_threads": h.cpu_threads or 1,
            "ram_mb": h.ram_mb or 1024,
            "disk_gb": 200,                # placeholder — real value from /nodes/<name>/storage
            "has_gpu": h.has_gpu,
            "gpu_model": h.gpu_model,
            "role_hint": role,
            "notes": h.notes,
        })

    workloads_yaml = []
    for w in result.proxmox_workloads:
        # Storage / pinned workloads (TrueNAS etc.) — pin them
        pin = None
        if w.tier == "storage" or "truenas" in w.name.lower():
            pin = w.current_host
        if "homeassistant" in w.name.lower() or "frigate" in w.name.lower():
            pin = w.current_host
        workloads_yaml.append({
            "name": w.name,
            "workload_id": w.workload_id,
            "workload_type": w.workload_type,
            "current_host": w.current_host,
            "ram_mb": w.ram_mb,
            "cpu_threads": w.cpu_threads,
            "needs_gpu": w.needs_gpu,
            "tier": w.tier,
            **({"pin_to_host": pin} if pin else {}),
            **({"notes": w.notes} if w.notes else {}),
        })

    fleet = {
        "name": result.fleet_name,
        "description": (
            f"Auto-discovered by `exo discover` on {result.discovered_at[:10]}.\n"
            f"{len(hosts_yaml)} hosts, {len(workloads_yaml)} workloads.\n"
            f"Refine RAM allocations or constraints by editing this file directly."
        ),
        "hosts": hosts_yaml,
        "workloads": workloads_yaml,
    }
    return fleet


def fleet_to_yaml(fleet: dict[str, Any]) -> str:
    """Render fleet dict to YAML text."""
    return yaml.safe_dump(fleet, sort_keys=False, default_flow_style=False, width=100)


def unmanaged_report(result: DiscoveryResult) -> dict[str, Any]:
    """Summarize unmanaged devices by tier for review."""
    by_tier: dict[str, list[dict]] = {}
    for c in result.classified:
        if c.tier == DeviceTier.MANAGED:
            continue
        by_tier.setdefault(c.tier.value, []).append({
            "ip": c.device.ip,
            "hostname": c.device.hostname,
            "open_ports": c.device.open_ports,
            "reason": c.reason,
        })
    return {
        "unmanaged_total": sum(len(v) for v in by_tier.values()),
        "by_tier": by_tier,
    }
