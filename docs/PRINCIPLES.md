# exo · framework grounding

Every algorithm in exo should map to a published framework. This document
is the audit trail — if a piece of behavior isn't grounded here, it's
either undocumented prior art (please file a PR adding the citation) or
we're inventing without justification (please file an issue).

Last reviewed: 2026-05-20

---

## `exo plan` — fleet rebalancing

Closest analogues: **Kubernetes scheduler** (descendant of Google's Borg
paper) and **VMware vSphere DRS**.

### Two-phase scheduling (Kubernetes)

The K8s scheduler runs every Pod through two phases:

1. **Filter** — which nodes CAN host this Pod (capacity, hard constraints,
   taints/tolerations). Anything that fails any filter is excluded.
2. **Score** — among the surviving candidates, which node is BEST
   (utilization, affinity preference, soft constraints).

exo plan's `balancer.py` follows this split (`_can_place` = filter,
`_score_host` = score). Concept mapped directly. **Source:**
[Assigning Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/).

### Constraint vocabulary

| K8s primitive | exo plan field | What it does |
|---|---|---|
| `nodeSelector` / `nodeAffinity (required)` | `pin_to_host` | Hard: must land on named host |
| `nodeAffinity (preferred)` | `tier` + `role_hint` | Soft: prefer host whose role matches |
| Pod inter-affinity | `co_locate_with` | Soft: prefer same host as listed workloads |
| Pod inter-anti-affinity | `must_not_share_with` | Hard: cannot share host |
| Topology spread constraints | `spread_across` (planned) | Spread instances across failure domains |
| Pod Disruption Budget | migration-wave size cap | At most N can be moving at once |

**Source:** [Pod Topology Spread Constraints](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/).
**Source:** [Pod Disruption Budgets 2026 patterns](https://www.hostmycode.com/blog/kubernetes-pod-disruption-budgets-2026-advanced-cluster-reliability-patterns-zero-downtime-deployments).

### Cost model

VMware DRS pre-v7 used **standard deviation of host load** as the
imbalance metric. exo plan uses the same: `evaluate_placement()` returns
`variance` across hosts. Mean utilization minimized via score function.

vSphere 7+ moved to a richer **cost model** balancing CPU + memory +
network. exo plan currently uses RAM only — CPU added as of 2026-05-20;
network bandwidth is a known gap.

**Source:** [VMware DRS Overview](https://knowledge.broadcom.com/external/article/391137/vmware-drs-overview-optimizing-resource.html).
**Source:** [Waldspurger et al., VMware Distributed Resource Management](https://www.waldspurger.org/carl/papers/drs-vmtj-mar12.pdf) (the canonical paper).

### Bin-packing algorithm

exo plan uses **First Fit Decreasing (FFD)**: sort workloads by RAM
descending, place each on the highest-scoring host that fits. FFD has
a worst-case bound of `11/9 · OPT + 6/9` (Johnson 1973). Adequate for
sub-100-workload fleets; for larger we'd want **Integer Linear
Programming** via OR-tools.

### Capacity-safety primitives

- **Headroom reserve** — 15% of host RAM kept unallocated.
  Source: Google SRE Book §18 "Software Engineering in SRE" recommends
  20% headroom for unpredictable demand spikes; we use 15% because
  homelabs don't have the elasticity of cloud and most homelab spikes
  are predictable. **[MED — homelab-specific deviation]**
- **Hypervisor overhead** — 4 GB reserved per host for the Proxmox
  hypervisor itself, before any LXC/VM is placed. Empirical from PVE
  docs guidance for clusters under 64 GB.

---

## Migration plan — `exo plan` output

Maps to the **AWS / Gartner 7 Rs** framework:

| Strategy | When exo plan picks it |
|---|---|
| **Relocate** | Within-cluster `pct/qm migrate` — same OS, same shape, different host (today's default) |
| **Rehost** | Lift-and-shift to a new cluster (not yet implemented) |
| **Replatform** | LXC → VM, or version upgrade during move (planned via `migration_strategy: replatform`) |
| **Refactor** | Re-architect into a different shape — exo plan won't propose this; flag for the human |
| **Repurchase** | Replace with a SaaS — `exo recommend` territory, not plan |
| **Retire** | Workload no longer needed |
| **Retain** | Workload stays where it is (=pin_to_host) |

**Source:** [AWS Migration Strategies (Prescriptive Guidance)](https://docs.aws.amazon.com/prescriptive-guidance/latest/large-migration-guide/migration-strategies.html).
**Source:** [The 7 Rs of Cloud Migration (IBM)](https://www.ibm.com/think/insights/7-rs-cloud-migration).

### Wave sequencing — blast-radius first

The plan orders waves by **risk band**, low first. This mirrors the
**deployment frequency / blast radius** thinking in Accelerate (Forsgren,
Humble, Kim 2018): small batches, low-risk first, verify between waves.

It also maps to **Pod Disruption Budgets**: each wave is sized so that no
more than `steps_per_wave` workloads (default 3) are in motion at once.

---

## `exo solve` — diagnostic planning

Closest analogues: **Site Reliability Engineering** incident-response
mental models + **Cynefin** domain classification + **Bayesian
troubleshooting**.

- **Five Whys / fishbone** — exo solve's hypothesis chain is a flat
  ordering of root-cause candidates. Should be a tree (planned: Phase
  C2 in v0.4 backlog).
- **Information-gain ranking** — current ranking is "cheapest-first"
  (Phase C1 will switch to entropy reduction; this aligns with classic
  diagnostic search theory from Pearl 1988 and the more recent
  Active-Probing literature).
- **Cynefin** — Snowden's framework (Clear / Complicated / Complex /
  Chaotic) — exo solve currently treats every problem as Complicated.
  Routing Complex problems to probe-sense-respond is planned (Phase C2).

**Sources:**
- [Cynefin framework, Wikipedia](https://en.wikipedia.org/wiki/Cynefin_framework)
- [Google SRE Book §13 — Effective Troubleshooting](https://sre.google/sre-book/effective-troubleshooting/)

---

## `exo execute` — action loop

Closest analogues: **OODA loop** (Boyd) and **PDCA / Deming cycle**.

| OODA stage | exo execute step |
|---|---|
| Observe | Run diagnostic command (the `proposed_command`) |
| Orient | Parse stdout into signals (`parse_output`) |
| Decide | `_propose_next_step` picks the follow-up |
| Act | Run the follow-up (next iteration) |

The **Orient** step is the weakest today — it parses but doesn't update
a probabilistic model. Phase D (calibration loop) will add Bayesian
updating of hypothesis priors based on outcomes.

**Source:** [OODA Loop, Wikipedia](https://en.wikipedia.org/wiki/OODA_loop).
**Source:** [Plan–Do–Check–Act, Wikipedia](https://en.wikipedia.org/wiki/PDCA).

### Safety classification

Three-band (SAFE/CAUTION/DESTRUCTIVE) maps loosely to **NIST SP 800-53
control families** for change classification — but with one homelab-
specific simplification: we classify by command verb pattern, not by
policy. A more rigorous version would consult a target-role catalog
(planned: Phase E contextual blast-radius).

---

## `exo recommend` — repo scoring

Closest analogues: **Analytic Hierarchy Process (AHP)** for multi-
criteria decision analysis, with weighted sub-scores summing to a
composite.

| AHP concept | exo recommend impl |
|---|---|
| Criteria | maintenance, popularity, governance, license_fit |
| Pairwise weights → priorities | weight_profile (default / reliable / cutting-edge / commercial) |
| Composite score | weighted sum of sub-scores |
| Consistency check | NOT YET implemented (planned) |

**Source:** [Analytic Hierarchy Process, Saaty 1980](https://en.wikipedia.org/wiki/Analytic_hierarchy_process).

The leaderboard is essentially AHP exposed as a public dataset.

---

## System description schema — fleet.yaml

Closest analogue: **C4 model — System Landscape** (Simon Brown).

The C4 model has four levels: Context, Containers, Components, Code.
exo's fleet.yaml currently models **System Landscape** (between Context
and Container in C4 terms):

- **Hosts** ≈ C4 "deployment nodes"
- **Workloads** ≈ C4 "containers" in the deployment sense
- **`dependency_group` / `co_locate_with`** ≈ C4 "relationships"
  (weak — currently same-host preference only, not direction or call-graph)

**Source:** [C4 model](https://c4model.com/).
**Source:** [System Landscape diagram](https://c4model.com/diagrams/system-landscape).

A Level-3 (Component) description would let `exo plan` reason about
service dependencies (e.g., "Authentik → NPM is a call edge, must
keep latency low → co-locate"). This is the planned next step beyond
v0.5.

---

## Discovery — `exo doctor` and `exo discover` (planned)

Closest analogue: **CMDB / IT Service Management discovery patterns**
(ITIL v4) — automated discovery of configuration items into a
configuration management database.

`exo doctor` today probes a small number of localhost services;
`exo discover <host>` (planned) would auto-build a fleet.yaml by:

- Querying Proxmox cluster API (`pvesh get /cluster/resources`)
- Per-LXC: `pct config <id>` for RAM/CPU allocation, mounts, USB
  pass-through (hardware pin signal)
- Per-VM: `qm config <id>` likewise
- Building the `dependency_group` weak graph from co-location

**Source:** [ITIL v4 Service Configuration Management](https://www.axelos.com/resource-hub/practice/service-configuration-management).

---

## What we deliberately don't do

- **No real-time scheduler.** exo plan is offline batch-planning, not
  K8s-style continuous reconciliation. The right comparison is `kubectl
  drain` + manual `kubectl uncordon`, not the live scheduler.
- **No live resource monitoring.** We read static fleet.yaml + the
  HOMELAB-INVENTORY snapshot. A future agent could subscribe to
  node-exporter metrics; until then we use audit-time snapshots.
- **No ML.** All rankings, scores, and recommendations are
  deterministic formulas with explicit weights. The user can audit
  every decision.

---

## Confidence per principle

| Principle | Confidence | Why |
|---|---|---|
| Two-phase scheduling | **HIGH** | Direct K8s mapping; verified in code |
| RAM cost model | **HIGH** | DRS pre-v7 exact analog |
| 15% headroom | **MED** | Homelab-specific deviation from Google's 20% |
| 4 GB hypervisor reserve | **MED** | Empirical; varies by Proxmox version |
| FFD bin-packing | **HIGH** | Well-known algorithm with known bounds |
| 7 Rs migration | **HIGH** | Industry-standard framework |
| Risk-band wave sequencing | **HIGH** | Aligns with Accelerate + PDB pattern |
| Cynefin in solve | **SPECULATIVE** | Not yet implemented (Phase C2) |
| OODA in execute | **MED** | Loose mapping; Orient step weak |
| AHP in recommend | **HIGH** | Recommend implements weighted multi-criteria |
| C4 system-landscape schema | **HIGH** | fleet.yaml directly mirrors C4 Level 1 |
| ITIL discovery for `exo discover` | **MED** | Planned, not built |

---

## Sources

Primary references this document leans on:

- [Kubernetes — Assigning Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)
- [Kubernetes — Pod Topology Spread Constraints](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/)
- [Pod Disruption Budgets 2026 patterns](https://www.hostmycode.com/blog/kubernetes-pod-disruption-budgets-2026-advanced-cluster-reliability-patterns-zero-downtime-deployments)
- [Waldspurger et al., VMware Distributed Resource Management](https://www.waldspurger.org/carl/papers/drs-vmtj-mar12.pdf)
- [VMware DRS Overview (Broadcom)](https://knowledge.broadcom.com/external/article/391137/vmware-drs-overview-optimizing-resource.html)
- [AWS Migration Strategies (Prescriptive Guidance)](https://docs.aws.amazon.com/prescriptive-guidance/latest/large-migration-guide/migration-strategies.html)
- [IBM — The 7 Rs of Cloud Migration](https://www.ibm.com/think/insights/7-rs-cloud-migration)
- [C4 model (Simon Brown)](https://c4model.com/)
- [Google SRE Book — Effective Troubleshooting](https://sre.google/sre-book/effective-troubleshooting/)
- [Cynefin framework](https://en.wikipedia.org/wiki/Cynefin_framework)
- [Analytic Hierarchy Process](https://en.wikipedia.org/wiki/Analytic_hierarchy_process)
- [OODA loop](https://en.wikipedia.org/wiki/OODA_loop)
