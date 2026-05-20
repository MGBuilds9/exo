"""Fleet description — hosts, workloads, constraints.

The YAML schema is intentionally simple. Hosts carry capacity. Workloads
carry resource demands + a current host + optional constraints. The whole
file is the ground truth — exo plan reads it, never mutates it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Host:
    """A physical host in the fleet."""
    name: str
    cpu_threads: int
    ram_mb: int
    disk_gb: int
    has_gpu: bool = False
    gpu_model: str = ""
    role_hint: str = ""        # "compute" / "storage" / "edge" / ""
    notes: str = ""
    # Computed at load time
    headroom_pct: float = 0.15  # reserve 15% capacity by default


@dataclass
class Workload:
    """A container/VM that needs a host.

    Schema grounded in C4 model 'container' nodes + Kubernetes Pod spec
    + AWS 7 Rs migration classification. See docs/PRINCIPLES.md.
    """
    name: str
    workload_id: str             # e.g. "ct-200", "vm-100"
    workload_type: str           # "lxc" / "vm" / "docker-host"
    current_host: str
    ram_mb: int                  # allocated RAM
    cpu_threads: int = 1         # K8s requests.cpu equivalent
    disk_gb: int = 8
    needs_gpu: bool = False
    pin_to_host: Optional[str] = None    # K8s nodeSelector / required affinity
    must_not_share_with: list[str] = field(default_factory=list)  # K8s pod anti-affinity (hard)
    co_locate_with: list[str] = field(default_factory=list)        # K8s pod affinity (soft)
    spread_across: str = ""       # K8s topologySpreadConstraints — e.g. "host" to spread instances
    dependency_group: str = ""    # workloads with same group prefer same host
    tier: str = "user"            # "edge" / "compute" / "user" / "storage" — maps to K8s nodeAffinity preferred
    migration_strategy: str = "relocate"  # 7 Rs: rehost/relocate/replatform/refactor/repurchase/retire/retain
    notes: str = ""

    @property
    def ram_estimated(self) -> bool:
        """True if RAM number is a placeholder, not a measured allocation."""
        return self.ram_mb == 0


@dataclass
class Fleet:
    """The whole fleet — hosts + workloads."""
    name: str
    hosts: list[Host] = field(default_factory=list)
    workloads: list[Workload] = field(default_factory=list)
    description: str = ""
    source_path: Optional[Path] = None

    def host_by_name(self, name: str) -> Optional[Host]:
        for h in self.hosts:
            if h.name == name:
                return h
        return None

    def workloads_on(self, host_name: str) -> list[Workload]:
        return [w for w in self.workloads if w.current_host == host_name]

    def total_workload_ram_on(self, host_name: str) -> int:
        return sum(w.ram_mb for w in self.workloads_on(host_name))


@dataclass
class ConstraintViolation:
    """A placement that violated a hard constraint."""
    workload: str
    target_host: str
    reason: str


def load_fleet(path: Path | str) -> Fleet:
    """Load and validate a fleet YAML."""
    p = Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    hosts = [Host(**h) for h in raw.get("hosts", [])]
    workloads = [Workload(**w) for w in raw.get("workloads", [])]
    fleet = Fleet(
        name=raw.get("name", p.stem),
        description=raw.get("description", ""),
        hosts=hosts,
        workloads=workloads,
        source_path=p,
    )
    _validate(fleet)
    return fleet


def _validate(fleet: Fleet) -> None:
    """Raise ValueError on any obviously-broken fleet description."""
    host_names = {h.name for h in fleet.hosts}
    for w in fleet.workloads:
        if w.current_host not in host_names:
            raise ValueError(
                f"Workload {w.name} has current_host={w.current_host!r} but no such host exists"
            )
        if w.pin_to_host and w.pin_to_host not in host_names:
            raise ValueError(
                f"Workload {w.name} pinned to {w.pin_to_host!r} but no such host"
            )
        if w.needs_gpu:
            gpu_hosts = [h.name for h in fleet.hosts if h.has_gpu]
            if not gpu_hosts:
                raise ValueError(
                    f"Workload {w.name} needs_gpu=True but no host has a GPU"
                )
