"""Lock the exo plan contract: capacity respected, hard constraints honored,
migration ordered by risk band, deterministic output."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from exo_runtime.plan.fleet import Fleet, Host, Workload, load_fleet
from exo_runtime.plan.balancer import (
    PlacementStrategy, balance_fleet, evaluate_placement, _usable_ram,
)
from exo_runtime.plan.migration import build_migration_plan


def _small_fleet():
    """Two hosts, four workloads. Simple deterministic case."""
    return Fleet(
        name="test",
        hosts=[
            Host(name="alpha", cpu_threads=16, ram_mb=32000, disk_gb=200,
                 has_gpu=True, gpu_model="rtx", role_hint="compute"),
            Host(name="bravo", cpu_threads=8, ram_mb=16000, disk_gb=100,
                 has_gpu=False, role_hint="user"),
        ],
        workloads=[
            Workload(name="gpu-svc", workload_id="100", workload_type="lxc",
                     current_host="bravo", ram_mb=2000, needs_gpu=True,
                     tier="compute"),
            Workload(name="big-svc", workload_id="101", workload_type="lxc",
                     current_host="alpha", ram_mb=8000, tier="user"),
            Workload(name="small-svc-a", workload_id="102", workload_type="lxc",
                     current_host="alpha", ram_mb=1000, tier="user"),
            Workload(name="small-svc-b", workload_id="103", workload_type="lxc",
                     current_host="alpha", ram_mb=1000, tier="user"),
        ],
    )


def test_gpu_workload_lands_on_gpu_host():
    fleet = _small_fleet()
    p = balance_fleet(fleet, strategy=PlacementStrategy.SPECIALIZED)
    assert p.assignments["gpu-svc"] == "alpha"
    assert not p.violations


def test_specialized_strategy_prefers_role_match():
    """At least the first user-tier workload should land on the user-role host;
    later workloads may spill if the specialty host fills up — that's OK."""
    fleet = _small_fleet()
    # Shrink workloads so they fit on bravo (16000 MB - 4096 hyp - 15% headroom ≈ 9504 usable)
    for w in fleet.workloads:
        if w.tier == "user":
            w.ram_mb = 2000
    p = balance_fleet(fleet, strategy=PlacementStrategy.SPECIALIZED)
    user_assignments = [p.assignments[w.name] for w in fleet.workloads if w.tier == "user"]
    # At least one user-tier workload should be on the user-role host
    assert "bravo" in user_assignments, \
        f"specialized strategy should place at least one user-tier on bravo, got {user_assignments}"


def test_pin_to_host_honored():
    fleet = _small_fleet()
    fleet.workloads[1].pin_to_host = "alpha"
    p = balance_fleet(fleet, strategy=PlacementStrategy.SPECIALIZED)
    assert p.assignments[fleet.workloads[1].name] == "alpha"


def test_capacity_violation_recorded_not_silenced():
    """Try to over-pack a tiny host; should record violations not crash."""
    fleet = Fleet(
        name="tight",
        hosts=[Host(name="tiny", cpu_threads=2, ram_mb=8000, disk_gb=20)],
        workloads=[
            Workload(name="a", workload_id="1", workload_type="lxc",
                     current_host="tiny", ram_mb=5000),
            Workload(name="b", workload_id="2", workload_type="lxc",
                     current_host="tiny", ram_mb=5000),
        ],
    )
    p = balance_fleet(fleet)
    # 8000 MB total, 4000 host reserve, 15% headroom = ~2800 usable
    # Both 5000-MB workloads won't fit
    assert len(p.violations) >= 1


def test_no_op_when_already_balanced():
    """If current placement already meets all constraints, no moves."""
    fleet = _small_fleet()
    fleet.workloads[0].current_host = "alpha"  # GPU svc already on GPU host
    # Move the user-tier workloads to bravo so they're already specialized
    for w in fleet.workloads:
        if w.tier == "user":
            w.current_host = "bravo"
            w.ram_mb = 1000  # shrink so they fit on bravo
    p = balance_fleet(fleet, strategy=PlacementStrategy.SPECIALIZED)
    migration = build_migration_plan(fleet, p)
    moves = sum(len(w.steps) for w in migration.waves)
    assert moves == 0


def test_migration_waves_are_banded_by_risk():
    """No wave should contain mixed risk bands."""
    fleet = _small_fleet()
    # Force every workload to need to move
    for w in fleet.workloads:
        w.current_host = "alpha" if w.current_host == "bravo" else "bravo"
    p = balance_fleet(fleet, strategy=PlacementStrategy.SPECIALIZED)
    migration = build_migration_plan(fleet, p, steps_per_wave=10)
    for wave in migration.waves:
        risks = [s.risk_score for s in wave.steps]
        if not risks:
            continue
        # All risks should be in the same band: 0-4, 5-7, or 8-10
        bands = {(0 if r <= 4 else (1 if r <= 7 else 2)) for r in risks}
        assert len(bands) == 1, \
            f"Wave {wave.wave_n} mixes risk bands: risks={risks}, label={wave.label}"


def test_evaluate_placement_metrics_sane():
    fleet = _small_fleet()
    p = balance_fleet(fleet, strategy=PlacementStrategy.BALANCED)
    metrics = evaluate_placement(p, fleet)
    assert 0 <= metrics["util_min"] <= 100
    assert 0 <= metrics["util_max"] <= 100
    assert metrics["util_min"] <= metrics["util_max"]
    assert metrics["workloads_placed"] == 4


def test_usable_ram_subtracts_overhead_and_headroom():
    h = Host(name="x", cpu_threads=4, ram_mb=16000, disk_gb=100)
    # 16000 - 4096 (proxmox overhead) - 15% headroom (2400) = 9504
    assert _usable_ram(h) == 9504


def test_load_fleet_validates_unknown_host_reference():
    """A workload referencing a nonexistent host should raise."""
    import tempfile
    yaml_text = """
name: bad
hosts:
  - name: alpha
    cpu_threads: 4
    ram_mb: 8000
    disk_gb: 50
workloads:
  - name: orphan
    workload_id: "1"
    workload_type: lxc
    current_host: ghost-host
    ram_mb: 1000
"""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(yaml_text)
        path = f.name
    with pytest.raises(ValueError, match="ghost-host"):
        load_fleet(path)


def test_migration_strategy_retain_keeps_workload_put():
    """7 Rs 'retain' should keep the workload on its current host even if
    rebalancing would move it."""
    fleet = _small_fleet()
    # Put big-svc on alpha (its current host), mark it retain
    fleet.workloads[1].current_host = "alpha"
    fleet.workloads[1].migration_strategy = "retain"
    p = balance_fleet(fleet, strategy=PlacementStrategy.SPECIALIZED)
    assert p.assignments["big-svc"] == "alpha"


def test_migration_strategy_retire_excludes_from_placement():
    """7 Rs 'retire' workloads should not appear in assignments at all."""
    fleet = _small_fleet()
    fleet.workloads[2].migration_strategy = "retire"
    p = balance_fleet(fleet)
    assert "small-svc-a" not in p.assignments


def test_cpu_oversubscription_limit_enforced():
    """A host can be RAM-fine but CPU-overcommitted — filter should reject."""
    fleet = Fleet(
        name="cpu-tight",
        hosts=[Host(name="t", cpu_threads=2, ram_mb=64000, disk_gb=200)],
        workloads=[
            Workload(name=f"hot-{i}", workload_id=str(i), workload_type="lxc",
                     current_host="t", ram_mb=500, cpu_threads=2)
            for i in range(5)  # 5 workloads * 2 cpu = 10 cpu, host has 2*2=4 budget
        ],
    )
    p = balance_fleet(fleet)
    # 2 fit (4 cpu used), 3 violate
    assert len(p.violations) >= 3
    for v in p.violations:
        assert "CPU" in v.reason


def test_topology_spread_across_host_separates_peers():
    """Workloads with spread_across=host + same dependency_group should
    land on different hosts."""
    fleet = Fleet(
        name="spread",
        hosts=[
            Host(name="a", cpu_threads=8, ram_mb=32000, disk_gb=100),
            Host(name="b", cpu_threads=8, ram_mb=32000, disk_gb=100),
        ],
        workloads=[
            Workload(name="dns-1", workload_id="1", workload_type="lxc",
                     current_host="a", ram_mb=1000,
                     spread_across="host", dependency_group="dns"),
            Workload(name="dns-2", workload_id="2", workload_type="lxc",
                     current_host="a", ram_mb=1000,
                     spread_across="host", dependency_group="dns"),
        ],
    )
    p = balance_fleet(fleet)
    assert p.assignments["dns-1"] != p.assignments["dns-2"], \
        "dns-1 and dns-2 should land on different hosts (topology spread)"


def test_evaluate_placement_exposes_cpu_and_physical_metrics():
    """The new metrics — cpu_util and physical_util — should be returned."""
    fleet = _small_fleet()
    p = balance_fleet(fleet, strategy=PlacementStrategy.BALANCED)
    m = evaluate_placement(p, fleet)
    assert "cpu_util_mean" in m
    assert "cpu_util_max" in m
    assert "physical_util_max" in m
    assert "high_util_hosts" in m


def test_load_fleet_validates_gpu_needs_when_no_gpu_host():
    import tempfile
    yaml_text = """
name: gpuless
hosts:
  - name: alpha
    cpu_threads: 4
    ram_mb: 8000
    disk_gb: 50
workloads:
  - name: needs-gpu
    workload_id: "1"
    workload_type: lxc
    current_host: alpha
    ram_mb: 1000
    needs_gpu: true
"""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(yaml_text)
        path = f.name
    with pytest.raises(ValueError, match="needs_gpu"):
        load_fleet(path)
