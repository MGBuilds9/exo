"""Build an action plan for top-ranked issues.

For each issue:
- Diagnosis (what we think is wrong, based on evidence + concerns)
- 3 hypothesis options ranked by cheapness-to-test
- First concrete action (a command or step)
- Verification approach
- Rollback if applicable
- Optional: a capability slug + recommended-repo call if a new tool is needed

The plan is structured (no LLM in the loop for the core fields). An LLM
optional `synthesize_clarifications` enriches the questions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .reader import IssueCandidate


@dataclass
class ActionStep:
    description: str
    command: Optional[str] = None
    verification: Optional[str] = None
    rollback: Optional[str] = None
    needs_consent: bool = True


@dataclass
class IssuePlan:
    issue: IssueCandidate
    diagnosis: str
    hypotheses: list[str]
    first_action: ActionStep
    follow_up_actions: list[ActionStep] = field(default_factory=list)
    recommended_capability: Optional[str] = None
    clarifying_questions: list[str] = field(default_factory=list)


@dataclass
class ActionPlan:
    source_path: str
    issues_evaluated: int
    issues_in_plan: int
    plans: list[IssuePlan] = field(default_factory=list)


# === Plan templates by component type =========================================

def _diagnose_proxmox_host(issue: IssueCandidate) -> tuple[str, list[str], ActionStep]:
    diag = (f"Proxmox host '{issue.name}' is reporting {issue.issue_type}. "
            f"Most common root causes for Proxmox hosts in this state: "
            f"NFS / backup-target staleness, storage.cfg drift, kernel-update reboot pending, "
            f"or physical hardware (SSD / NIC).")
    hypotheses = [
        "Backup-target mount has gone stale (cheapest to test — `pvesm status`)",
        "Lost NFS share / storage.cfg drift (test via `mount | grep nfs` + tail syslog)",
        "Pending kernel reboot blocking new VM operations (test via `uptime` + `needrestart -k`)",
    ]
    first = ActionStep(
        description=f"Probe storage state on {issue.name} (read-only).",
        command=f"ssh root@{issue.name} 'pvesm status; mount | grep nfs; tail -50 /var/log/syslog | grep -i nfs'",
        verification="Look for: `pvesm status` showing any storage as inactive, NFS mounts in stale state, syslog NFS timeouts.",
        rollback=None,
        needs_consent=True,
    )
    return diag, hypotheses, first


def _diagnose_lxc(issue: IssueCandidate) -> tuple[str, list[str], ActionStep]:
    diag = (f"LXC container '{issue.name}' is reporting {issue.issue_type}. "
            f"For containers, the typical cause is resource pressure (memory/disk), "
            f"network-bind issue, or a service inside the container crashed.")
    hypotheses = [
        "Container OOM or disk full (cheapest — check `pct status` + `df` inside)",
        "Service inside container failed (test via service-specific health endpoint)",
        "Network binding issue post-host-restart (test via `pct config` + `ip a` inside)",
    ]
    first = ActionStep(
        description=f"Get container state + resource pressure for {issue.name}.",
        command=f"pct status <id> && pct exec <id> -- bash -c 'free -m; df -h; systemctl --failed'",
        verification="Look for failed systemd units, >85% memory or disk, container in stopped state.",
        rollback=None,
        needs_consent=True,
    )
    return diag, hypotheses, first


def _diagnose_storage(issue: IssueCandidate) -> tuple[str, list[str], ActionStep]:
    diag = (f"Storage host '{issue.name}' is reporting {issue.issue_type}. "
            f"For storage hosts, primary suspects are: ZFS pool degradation, "
            f"NFS/SMB session pressure, disk space, snapshot bloat.")
    hypotheses = [
        "ZFS pool degraded (cheapest — `zpool status`)",
        "NFS session storm from a dependent host (test via `nfsstat`)",
        "Snapshot backlog filling space (test via `zfs list -t snapshot`)",
    ]
    first = ActionStep(
        description=f"Probe ZFS + NFS state on {issue.name}.",
        command="zpool status -v; nfsstat -c | head; df -h",
        verification="Look for any pool not ONLINE, NFS retransmission counts climbing.",
        rollback=None,
        needs_consent=True,
    )
    return diag, hypotheses, first


def _diagnose_router(issue: IssueCandidate) -> tuple[str, list[str], ActionStep]:
    diag = (f"Router '{issue.name}' is reporting {issue.issue_type}. "
            f"For routers, primary suspects are: WAN saturation, firewall-rule drift, "
            f"DNS upstream failure.")
    hypotheses = [
        "WAN saturation or ISP outage (cheapest — speedtest from router)",
        "Firewall rule blocking expected traffic (test via rule logs)",
        "DNS upstream failure (test via `dig @upstream`)",
    ]
    first = ActionStep(
        description=f"Probe WAN + DNS state on {issue.name}.",
        command="check router admin UI for WAN status; from another host: dig @<router-ip> example.com",
        verification="WAN link up, no dropped packets, DNS query returns in <100ms.",
        rollback=None,
        needs_consent=True,
    )
    return diag, hypotheses, first


def _diagnose_generic(issue: IssueCandidate) -> tuple[str, list[str], ActionStep]:
    diag = (f"Component '{issue.name}' ({issue.component_type or 'unknown type'}) is "
            f"in {issue.issue_type} state. No type-specific diagnostic template available — "
            f"defaulting to general health probe.")
    hypotheses = [
        "Service-specific health endpoint is reporting unhealthy (most likely)",
        "Underlying host has resource pressure",
        "Recent config change broke the service",
    ]
    first = ActionStep(
        description=f"Pull recent logs + health state for {issue.name}.",
        command=f"# component-specific — need clarification on how this is hosted",
        verification="Read first 50 lines of error logs; check service status.",
        rollback=None,
        needs_consent=True,
    )
    return diag, hypotheses, first


# === Plan orchestration ========================================================

def _capability_hint(issue: IssueCandidate) -> Optional[str]:
    """If the proposed fix would benefit from a new tool, suggest a capability
    slug for `exo recommend` to score."""
    text = (issue.description + " " + " ".join(issue.suggested_fix_hints)).lower()
    if "monitor" in text or "observability" in text or "tracing" in text:
        return "observability"
    if "memory" in text and ("agent" in text or "rag" in text):
        return "memory-tier"
    return None


def _diagnose(issue: IssueCandidate) -> tuple[str, list[str], ActionStep]:
    ct = (issue.component_type or "").lower()
    if "proxmox" in ct:
        return _diagnose_proxmox_host(issue)
    if "lxc" in ct or "container" in ct:
        return _diagnose_lxc(issue)
    if "storage" in ct or "truenas" in ct.replace("-", "") or "nas" in ct:
        return _diagnose_storage(issue)
    if "router" in ct or "gateway" in ct:
        return _diagnose_router(issue)
    return _diagnose_generic(issue)


def _clarifications(issue: IssueCandidate) -> list[str]:
    """Default clarifying questions per issue. Rule-based, not LLM."""
    return [
        f"Have you already filed {issue.name} as a known-and-accepted issue (i.e., do NOT propose work)?",
        f"What's your constraint for fixing {issue.name}? (no-downtime / scheduled-window / fix-now-cost-be-damned)",
        f"Is there anything I should know about {issue.name}'s history that the topology data doesn't show?",
    ]


def build_plan(digest, top_n: int = 5) -> ActionPlan:
    """Build an ActionPlan from a DataDigest.

    Args:
        digest: DataDigest from reader.read_data_source
        top_n: How many top-ranked issues to plan for.
    """
    from .ranker import rank_issues

    ranked = rank_issues(digest.issues, top_n=top_n)
    plans = []
    for issue, composite in ranked:
        diag, hyps, first = _diagnose(issue)
        plan = IssuePlan(
            issue=issue,
            diagnosis=diag,
            hypotheses=hyps,
            first_action=first,
            follow_up_actions=[],
            recommended_capability=_capability_hint(issue),
            clarifying_questions=_clarifications(issue),
        )
        plans.append(plan)

    return ActionPlan(
        source_path=digest.source_path,
        issues_evaluated=len(digest.issues),
        issues_in_plan=len(plans),
        plans=plans,
    )
