"""Bin-pack workloads onto hosts subject to constraints.

Two-phase scheduling, modeled on the Kubernetes scheduler:
  Phase 1 — FILTER  (which hosts CAN host this workload)
  Phase 2 — SCORE   (among candidates, which host is BEST)

See docs/PRINCIPLES.md §"exo plan" for the framework mapping.

Strategies:
- balanced     — minimize utilization variance across hosts (VMware DRS imbalance metric)
- specialized  — prefer host whose role_hint matches workload tier; fall back to balanced
- consolidated — pack tightly onto fewest hosts (lets you free up a host)

Algorithm (greedy First Fit Decreasing with constraints):
1. Pass 1: place hard-constrained workloads first (pin_to_host, needs_gpu).
2. Pass 2: remaining workloads in descending RAM order.
3. For each, run FILTER → SCORE → place on top-scoring host.
4. If no host survives FILTER, record a ConstraintViolation and continue.

Cost model:
- Primary: RAM (matches DRS pre-v7 and current homelab bottleneck)
- Secondary: CPU threads (DRS-v7-style soft pressure check)
- Future: network bandwidth (gap — see PRINCIPLES.md)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .fleet import Fleet, Host, Workload, ConstraintViolation


class PlacementStrategy(str, Enum):
    BALANCED = "balanced"
    SPECIALIZED = "specialized"
    CONSOLIDATED = "consolidated"


@dataclass
class Placement:
    """A proposed placement of every workload onto a host."""
    strategy: PlacementStrategy
    assignments: dict[str, str] = field(default_factory=dict)  # workload.name -> host.name
    violations: list[ConstraintViolation] = field(default_factory=list)
    host_ram_used: dict[str, int] = field(default_factory=dict)
    host_cpu_used: dict[str, int] = field(default_factory=dict)
    host_workload_count: dict[str, int] = field(default_factory=dict)

    def moves(self, fleet: Fleet) -> list[tuple[Workload, str, str]]:
        """List of (workload, from_host, to_host) for workloads that move."""
        out = []
        for w in fleet.workloads:
            target = self.assignments.get(w.name)
            if target and target != w.current_host:
                out.append((w, w.current_host, target))
        return out


def _usable_ram(host: Host) -> int:
    """RAM after subtracting headroom + a fixed Proxmox host reserve."""
    proxmox_overhead = 4096  # MB for the hypervisor itself
    headroom = int(host.ram_mb * host.headroom_pct)
    return max(0, host.ram_mb - proxmox_overhead - headroom)


def _filter(workload: Workload, host: Host, current_assignments: dict[str, str],
            fleet: Fleet, ram_used: dict[str, int],
            cpu_used: dict[str, int]) -> tuple[bool, str]:
    """K8s-style FILTER phase: return (ok, reason).

    A host that fails any check here is excluded from consideration.
    """
    # Hard constraint: ownership boundary
    # If a host has an `owner`, it is a strict allowlist — only workloads with a
    # matching owner can land there. Ownerless workloads CANNOT use owned hosts
    # (treated as foreign). Hosts without an owner accept any workload.
    # Maps to organizational boundaries (multi-tenant homelabs, family servers).
    if host.owner and workload.owner != host.owner:
        if workload.owner:
            return False, f"ownership: {host.owner}'s host won't accept {workload.owner}'s workload"
        return False, f"ownership: {host.owner}'s host requires matching owner tag"
    # Hard constraint: pinning
    if workload.pin_to_host and workload.pin_to_host != host.name:
        return False, f"pinned to {workload.pin_to_host}"
    # Hard constraint: GPU requirement
    if workload.needs_gpu and not host.has_gpu:
        return False, "needs GPU"
    # Capacity: RAM
    if ram_used.get(host.name, 0) + workload.ram_mb > _usable_ram(host):
        return False, "no RAM headroom"
    # Capacity: CPU threads (soft pressure — allow up to 2x oversubscription)
    cpu_budget = host.cpu_threads * 2
    if cpu_used.get(host.name, 0) + workload.cpu_threads > cpu_budget:
        return False, f"CPU oversubscription >2x ({host.cpu_threads} threads available)"
    # Hard anti-affinity
    cohabitants = [w_name for w_name, h_name in current_assignments.items()
                   if h_name == host.name]
    for forbidden in workload.must_not_share_with:
        if forbidden in cohabitants:
            return False, f"anti-affinity with {forbidden}"
    # Topology spread: if workload says spread_across=host and a same-group
    # peer is already here, skip this host (soft-but-treated-as-filter for now)
    if workload.spread_across == "host" and workload.dependency_group:
        for w_name, h_name in current_assignments.items():
            if h_name != host.name:
                continue
            peer = next((w for w in fleet.workloads if w.name == w_name), None)
            if peer and peer.dependency_group == workload.dependency_group:
                return False, f"topology spread: {peer.name} (same group) already here"
    return True, ""


# Backward-compatible alias for existing tests/code
_can_place = _filter


def _score_host(workload: Workload, host: Host, strategy: PlacementStrategy,
                ram_used: dict[str, int], current_assignments: dict[str, str]) -> float:
    """Higher is better."""
    usable = _usable_ram(host)
    used = ram_used.get(host.name, 0)
    free = usable - used
    util = used / usable if usable > 0 else 1.0

    if strategy == PlacementStrategy.BALANCED:
        # Prefer host with most free RAM (level utilization)
        score = free
    elif strategy == PlacementStrategy.CONSOLIDATED:
        # Prefer host with least free RAM that still fits (pack tightly)
        score = -free
    else:  # SPECIALIZED
        # Specialty match boost; fall back to balanced
        score = free
        if host.role_hint and host.role_hint == workload.tier:
            score += 100_000  # massive boost — always prefer specialty match
        # GPU host preferred for GPU work (redundant with hard constraint but useful for soft pref)
        if workload.needs_gpu and host.has_gpu:
            score += 50_000

    # Co-location preference (any strategy)
    if workload.co_locate_with or workload.dependency_group:
        # Boost if a buddy is already on this host
        for w_name, h_name in current_assignments.items():
            if h_name != host.name:
                continue
            buddy = next((b for b in [workload.co_locate_with] if w_name in b), None)
            if buddy:
                score += 10_000
            # Same dependency_group: weak boost
            # (We can't see other workload's group from here without fleet ref;
            #  caller handles dependency-group via a post-pass if needed.)
    return score


def balance_fleet(fleet: Fleet,
                  strategy: PlacementStrategy = PlacementStrategy.SPECIALIZED) -> Placement:
    """Compute a proposed placement using two-phase scheduling.

    Phase 1: place hard-constrained workloads (pin_to_host, needs_gpu, retain).
    Phase 2: place remaining via First Fit Decreasing (largest RAM first).
    Each placement: filter candidates, then score, then pick best.
    """
    placement = Placement(strategy=strategy)
    ram_used: dict[str, int] = {h.name: 0 for h in fleet.hosts}
    cpu_used: dict[str, int] = {h.name: 0 for h in fleet.hosts}
    wl_count: dict[str, int] = {h.name: 0 for h in fleet.hosts}

    def _commit(w: Workload, host: Host) -> None:
        placement.assignments[w.name] = host.name
        ram_used[host.name] += w.ram_mb
        cpu_used[host.name] += w.cpu_threads
        wl_count[host.name] += 1

    # Pass 1: hard-constrained workloads (pinned, GPU-required, or migration=retain)
    remaining: list[Workload] = []
    for w in fleet.workloads:
        # 7 Rs: retain means stay put no matter what
        if w.migration_strategy == "retain":
            host = fleet.host_by_name(w.current_host)
            if host:
                ok, reason = _filter(w, host, placement.assignments, fleet, ram_used, cpu_used)
                if ok:
                    _commit(w, host)
                else:
                    placement.violations.append(ConstraintViolation(
                        w.name, host.name, f"retain but {reason}"))
            continue
        # 7 Rs: retire means drop from placement
        if w.migration_strategy == "retire":
            continue

        if w.pin_to_host:
            host = fleet.host_by_name(w.pin_to_host)
            if not host:
                placement.violations.append(ConstraintViolation(
                    w.name, w.pin_to_host or "?", "pin_to_host references unknown host"))
                continue
            ok, reason = _filter(w, host, placement.assignments, fleet, ram_used, cpu_used)
            if not ok:
                placement.violations.append(ConstraintViolation(w.name, host.name, reason))
                continue
            _commit(w, host)
        elif w.needs_gpu:
            gpu_hosts = [h for h in fleet.hosts if h.has_gpu]
            placed = False
            for host in gpu_hosts:
                ok, reason = _filter(w, host, placement.assignments, fleet, ram_used, cpu_used)
                if ok:
                    _commit(w, host)
                    placed = True
                    break
            if not placed:
                placement.violations.append(ConstraintViolation(
                    w.name, "(any GPU host)", "no GPU host has capacity"))
        else:
            remaining.append(w)

    # Pass 2: First Fit Decreasing — biggest first, filter → score → place
    remaining.sort(key=lambda w: -w.ram_mb)
    for w in remaining:
        # FILTER (capture reasons so we can report why nothing fit)
        candidates = []
        rejection_reasons: list[str] = []
        for host in fleet.hosts:
            ok, reason = _filter(w, host, placement.assignments, fleet, ram_used, cpu_used)
            if ok:
                candidates.append(host)
            else:
                rejection_reasons.append(f"{host.name}: {reason}")
        if not candidates:
            summary = "; ".join(rejection_reasons[:3])
            placement.violations.append(ConstraintViolation(
                w.name, "(none)", f"no host survives filter — {summary}"))
            continue
        # SCORE
        scored = [(_score_host(w, h, strategy, ram_used, placement.assignments), h)
                  for h in candidates]
        scored.sort(key=lambda c: -c[0])
        _commit(w, scored[0][1])

    placement.host_ram_used = ram_used
    placement.host_cpu_used = cpu_used
    placement.host_workload_count = wl_count
    return placement


def evaluate_placement(placement: Placement, fleet: Fleet) -> dict:
    """Return a metrics dict describing the placement quality.

    Includes both RAM and CPU utilization metrics. The `variance` metric
    mirrors VMware DRS pre-v7's imbalance metric (stddev of host load).
    """
    ram_pcts = []
    cpu_pcts = []
    physical_pcts = []   # against raw RAM, not usable — for human sanity check
    for host in fleet.hosts:
        ram_used = placement.host_ram_used.get(host.name, 0)
        cpu_used = placement.host_cpu_used.get(host.name, 0)
        usable_ram = _usable_ram(host)
        if usable_ram > 0:
            ram_pcts.append(ram_used / usable_ram * 100)
        if host.ram_mb > 0:
            physical_pcts.append(ram_used / host.ram_mb * 100)
        if host.cpu_threads > 0:
            cpu_pcts.append(cpu_used / host.cpu_threads * 100)
    if not ram_pcts:
        return {"util_max": 0, "util_min": 0, "util_mean": 0, "variance": 0,
                "violations": len(placement.violations),
                "workloads_placed": len(placement.assignments)}
    mean = sum(ram_pcts) / len(ram_pcts)
    variance = sum((p - mean) ** 2 for p in ram_pcts) / len(ram_pcts)
    metrics = {
        "util_max": round(max(ram_pcts), 1),
        "util_min": round(min(ram_pcts), 1),
        "util_mean": round(mean, 1),
        "variance": round(variance, 1),
        "violations": len(placement.violations),
        "workloads_placed": len(placement.assignments),
        "workloads_total": len(fleet.workloads),
        "cpu_util_max": round(max(cpu_pcts), 1) if cpu_pcts else 0,
        "cpu_util_mean": round(sum(cpu_pcts) / len(cpu_pcts), 1) if cpu_pcts else 0,
        "physical_util_max": round(max(physical_pcts), 1) if physical_pcts else 0,
    }
    # Capacity warning: physical >85% is unsafe even though we have headroom
    metrics["high_util_hosts"] = [
        h.name for h in fleet.hosts
        if h.ram_mb > 0
        and placement.host_ram_used.get(h.name, 0) / h.ram_mb > 0.85
    ]
    return metrics
