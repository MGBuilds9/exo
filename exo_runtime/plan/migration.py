"""Build a migration plan from current state to target placement.

Maps to AWS / Gartner 7 Rs migration framework (see docs/PRINCIPLES.md).
Most exo plan moves are "Relocate" (within-cluster pct/qm migrate); the
workload's `migration_strategy` field overrides per-workload.

Wave sequencing follows Accelerate's small-batch principle + Kubernetes
Pod Disruption Budgets: lowest-blast-radius first, each wave capped at
`steps_per_wave` concurrent moves, banded by risk so a wave never mixes
trivial and spine-critical changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .balancer import Placement
from .fleet import Fleet, Workload


CRITICAL_NAME_HINTS = {
    "authentik", "nginxproxymanager", "npm", "adguard", "pihole",
    "truenas", "storage", "homeassistant", "dns",
}


@dataclass
class MigrationStep:
    workload: Workload
    from_host: str
    to_host: str
    risk_score: int
    risk_reason: str
    strategy: str = "relocate"   # 7 Rs classification
    proposed_commands: list[str] = field(default_factory=list)
    rollback_commands: list[str] = field(default_factory=list)


@dataclass
class MigrationWave:
    wave_n: int
    label: str
    steps: list[MigrationStep] = field(default_factory=list)


@dataclass
class MigrationPlan:
    fleet_name: str
    strategy: str
    waves: list[MigrationWave] = field(default_factory=list)
    no_op_workloads: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)


def _risk_score(workload: Workload) -> tuple[int, str]:
    """Score 0..10. 0 = trivial, 10 = production spine."""
    name = workload.name.lower()
    if any(hint in name for hint in CRITICAL_NAME_HINTS):
        return 9, "critical infrastructure (auth/proxy/dns/storage)"
    if workload.tier == "storage":
        return 8, "storage tier"
    if workload.tier == "edge":
        return 6, "edge/IoT tier"
    if workload.tier == "compute":
        return 4, "compute tier (rebuildable)"
    if workload.tier == "user":
        return 3, "user-facing service"
    return 5, "unclassified — assume medium"


def _proposed_commands(workload: Workload, from_host: str, to_host: str) -> list[str]:
    """Generate the actual shell commands. Assumes Proxmox cluster online migration."""
    wid = workload.workload_id
    if workload.workload_type == "lxc":
        return [
            f"# On {from_host}:",
            f"ssh root@{from_host} 'pct migrate {wid} {to_host} --restart 1'",
            f"# Verify:",
            f"ssh root@{to_host} 'pct status {wid}'",
        ]
    if workload.workload_type == "vm":
        return [
            f"# On {from_host}:",
            f"ssh root@{from_host} 'qm migrate {wid} {to_host} --online 1'",
            f"# Verify:",
            f"ssh root@{to_host} 'qm status {wid}'",
        ]
    return [f"# {workload.workload_type} migration not implemented — manual move"]


def _rollback_commands(workload: Workload, from_host: str, to_host: str) -> list[str]:
    """Reverse of the proposed commands."""
    wid = workload.workload_id
    if workload.workload_type == "lxc":
        return [
            f"# Roll back: move {wid} from {to_host} back to {from_host}",
            f"ssh root@{to_host} 'pct migrate {wid} {from_host} --restart 1'",
        ]
    if workload.workload_type == "vm":
        return [
            f"# Roll back: move {wid} from {to_host} back to {from_host}",
            f"ssh root@{to_host} 'qm migrate {wid} {from_host} --online 1'",
        ]
    return ["# manual rollback required"]


def build_migration_plan(fleet: Fleet, placement: Placement,
                          steps_per_wave: int = 3) -> MigrationPlan:
    plan = MigrationPlan(fleet_name=fleet.name, strategy=placement.strategy.value)

    moves = placement.moves(fleet)
    if not moves:
        return plan

    # Annotate with risk
    annotated: list[MigrationStep] = []
    for w, frm, to in moves:
        risk, reason = _risk_score(w)
        annotated.append(MigrationStep(
            workload=w, from_host=frm, to_host=to,
            risk_score=risk, risk_reason=reason,
            strategy=w.migration_strategy,
            proposed_commands=_proposed_commands(w, frm, to),
            rollback_commands=_rollback_commands(w, frm, to),
        ))

    # Sort by risk ascending — lowest-blast first
    annotated.sort(key=lambda s: s.risk_score)

    # Band-then-chunk: keep each wave inside one risk band, then split if oversized.
    bands = [
        (0, 4, "low-risk shakedown"),
        (5, 7, "medium-risk services"),
        (8, 10, "high-risk spine — extra care"),
    ]
    wave_n = 1
    for lo, hi, label in bands:
        band_steps = [s for s in annotated if lo <= s.risk_score <= hi]
        if not band_steps:
            continue
        for i in range(0, len(band_steps), steps_per_wave):
            batch = band_steps[i : i + steps_per_wave]
            suffix = "" if len(band_steps) <= steps_per_wave else f" (part {i // steps_per_wave + 1})"
            plan.waves.append(MigrationWave(
                wave_n=wave_n, label=label + suffix, steps=batch))
            wave_n += 1

    # Note workloads with no moves
    plan.no_op_workloads = [
        w.name for w in fleet.workloads
        if placement.assignments.get(w.name) == w.current_host
    ]
    plan.blocked = [v.workload for v in placement.violations]
    return plan
