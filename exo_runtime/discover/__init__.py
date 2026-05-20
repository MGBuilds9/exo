"""exo discover — auto-build fleet.yaml from live infrastructure.

Closes the V1 wedge: cold-install user gets a working plan in 60 seconds
without ever hand-editing YAML. Per docs/PRINCIPLES.md §"Discovery" this
follows ITIL v4 CMDB discovery patterns + Kubernetes' node-info shape.

Composes four streams:
- proxmox.py    — SSH-driven Proxmox cluster + per-workload config
- lan.py        — ping sweep + reverse DNS + courtesy port check
- inventory.py  — read HOMELAB-INVENTORY.md if present (preserves notes)
- classify.py   — sort unmanaged devices into tiers
- synth.py      — compose into fleet.yaml-compatible structure
"""
from .proxmox import probe_proxmox_cluster, ProxmoxHost, ProxmoxWorkload
from .lan import probe_lan_subnet, LanDevice
from .inventory import read_inventory, InventoryEntry
from .classify import classify_unmanaged, DeviceTier
from .synth import synthesize_fleet, DiscoveryResult

__all__ = [
    "probe_proxmox_cluster", "ProxmoxHost", "ProxmoxWorkload",
    "probe_lan_subnet", "LanDevice",
    "read_inventory", "InventoryEntry",
    "classify_unmanaged", "DeviceTier",
    "synthesize_fleet", "DiscoveryResult",
]
