"""Lock the discover contract: classification heuristics, fleet synthesis,
inventory parsing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from exo_runtime.discover.classify import (
    classify_unmanaged, DeviceTier, ClassifiedDevice,
)
from exo_runtime.discover.lan import LanDevice
from exo_runtime.discover.inventory import read_inventory, InventoryEntry
from exo_runtime.discover.synth import (
    synthesize_fleet, DiscoveryResult, fleet_to_yaml, unmanaged_report,
)
from exo_runtime.discover.proxmox import ProxmoxHost, ProxmoxWorkload


# ---------------- classify ----------------

def test_classify_managed_device():
    devices = [LanDevice(ip="192.168.0.19", alive=True, hostname="mkgbuilds.lan")]
    result = classify_unmanaged(devices, inventory_ips={"192.168.0.19"}, managed_hosts=set())
    assert result[0].tier == DeviceTier.MANAGED


def test_classify_network_gear_low_octet():
    devices = [LanDevice(ip="192.168.0.1", alive=True),
               LanDevice(ip="192.168.0.14", alive=True)]
    result = classify_unmanaged(devices, inventory_ips=set(), managed_hosts=set())
    for r in result:
        assert r.tier == DeviceTier.NETWORK_GEAR


def test_classify_iot_pool():
    devices = [LanDevice(ip=f"192.168.0.{i}", alive=True) for i in (60, 75, 88, 99, 115)]
    result = classify_unmanaged(devices, inventory_ips=set(), managed_hosts=set())
    for r in result:
        assert r.tier == DeviceTier.IOT_POOL


def test_classify_end_user_by_hostname():
    devices = [
        LanDevice(ip="192.168.0.222", alive=True, hostname="MDM-Home-PC.local"),
        LanDevice(ip="192.168.0.225", alive=True, hostname="DGTL.local"),
    ]
    result = classify_unmanaged(devices, inventory_ips=set(), managed_hosts=set())
    for r in result:
        assert r.tier == DeviceTier.END_USER, f"{r.device.ip} {r.device.hostname} → {r.tier}"


def test_classify_keepalived_vip():
    """Michael's clarification: .29 is a Pi-hole HA VIP, not a third instance."""
    devices = [LanDevice(ip="192.168.0.29", alive=True, hostname="pi.hole")]
    result = classify_unmanaged(devices, inventory_ips=set(), managed_hosts=set())
    assert result[0].tier == DeviceTier.KEEPALIVED_VIP


def test_classify_npm_routed():
    devices = [LanDevice(ip="192.168.0.6", alive=True, hostname="DGTL-TrueNAS")]
    result = classify_unmanaged(devices, inventory_ips=set(),
                                managed_hosts=set(),
                                npm_routed_ips={"192.168.0.6"})
    assert result[0].tier == DeviceTier.NPM_ROUTED


def test_classify_unknown_fallback():
    devices = [LanDevice(ip="192.168.0.150", alive=True)]
    result = classify_unmanaged(devices, inventory_ips=set(), managed_hosts=set())
    assert result[0].tier == DeviceTier.UNKNOWN


# ---------------- inventory ----------------

def test_read_inventory_parses_michael_format(tmp_path):
    inv_text = """# Inventory

## Host Status Matrix

| Host | Status | Type | IP | Parent | Critical |
|------|--------|------|----|--------|----------|
| [mkgbuilds](homelab/mkgbuilds.md) | 🔴 red | proxmox-host | 192.168.0.19 | — |  |
| [dgtl-proxmox](homelab/dgtl-proxmox.md) | 🟡 yellow | proxmox-host | 192.168.0.5 | — |  |
| [authentik](homelab/ct-202-authentik.md) | 🟡 yellow | lxc | 192.168.0.42 | mkgbuilds |  |

## Other Section
"""
    f = tmp_path / "inv.md"
    f.write_text(inv_text, encoding="utf-8")
    inv = read_inventory(f)
    assert "192.168.0.19" in inv
    assert inv["192.168.0.19"].name == "mkgbuilds"
    assert inv["192.168.0.42"].parent == "mkgbuilds"


def test_read_inventory_missing_file():
    assert read_inventory("/no/such/path.md") == {}


# ---------------- synthesize ----------------

def test_synthesize_fleet_minimum():
    """A single host with two workloads should produce a usable fleet dict."""
    result = DiscoveryResult(
        fleet_name="test-fleet",
        proxmox_hosts=[
            ProxmoxHost(name="alpha", ip="192.168.0.10",
                       cpu_threads=8, ram_mb=32000, has_gpu=False),
        ],
        proxmox_workloads=[
            ProxmoxWorkload(name="nginx", workload_id="100", workload_type="lxc",
                           current_host="alpha", ram_mb=1024, cpu_threads=2,
                           tier="user"),
            ProxmoxWorkload(name="truenas", workload_id="200", workload_type="vm",
                           current_host="alpha", ram_mb=16384, cpu_threads=4,
                           tier="storage"),
        ],
    )
    fleet = synthesize_fleet(result)
    assert fleet["name"] == "test-fleet"
    assert len(fleet["hosts"]) == 1
    assert len(fleet["workloads"]) == 2
    # TrueNAS should be auto-pinned (storage tier)
    truenas = [w for w in fleet["workloads"] if w["name"] == "truenas"][0]
    assert truenas.get("pin_to_host") == "alpha"
    # nginx (user tier) should NOT be pinned
    nginx = [w for w in fleet["workloads"] if w["name"] == "nginx"][0]
    assert "pin_to_host" not in nginx


def test_synthesize_fleet_role_hint_from_gpu():
    """GPU host should get role_hint=compute."""
    result = DiscoveryResult(
        fleet_name="t",
        proxmox_hosts=[
            ProxmoxHost(name="gpu-box", ip="192.168.0.19", cpu_threads=32,
                       ram_mb=64000, has_gpu=True, gpu_model="RTX 3060"),
        ],
        proxmox_workloads=[],
    )
    fleet = synthesize_fleet(result)
    assert fleet["hosts"][0]["role_hint"] == "compute"


def test_fleet_to_yaml_roundtrip():
    """Synthesized YAML should be parseable back."""
    import yaml
    result = DiscoveryResult(
        fleet_name="roundtrip",
        proxmox_hosts=[ProxmoxHost(name="h", ip="1.1.1.1", cpu_threads=4, ram_mb=8000)],
        proxmox_workloads=[ProxmoxWorkload(name="w", workload_id="1",
                                          workload_type="lxc", current_host="h",
                                          ram_mb=1024)],
    )
    fleet = synthesize_fleet(result)
    yaml_text = fleet_to_yaml(fleet)
    parsed = yaml.safe_load(yaml_text)
    assert parsed["name"] == "roundtrip"
    assert parsed["hosts"][0]["name"] == "h"


def test_unmanaged_report_groups_by_tier():
    """The unmanaged report should bucket devices by tier with counts."""
    result = DiscoveryResult(
        fleet_name="t",
        classified=[
            ClassifiedDevice(
                device=LanDevice(ip="192.168.0.50", alive=True),
                tier=DeviceTier.IOT_POOL, reason="DHCP"),
            ClassifiedDevice(
                device=LanDevice(ip="192.168.0.51", alive=True),
                tier=DeviceTier.IOT_POOL, reason="DHCP"),
            ClassifiedDevice(
                device=LanDevice(ip="192.168.0.1", alive=True),
                tier=DeviceTier.NETWORK_GEAR, reason="gateway"),
            ClassifiedDevice(
                device=LanDevice(ip="192.168.0.19", alive=True),
                tier=DeviceTier.MANAGED, reason="in inventory"),
        ],
    )
    report = unmanaged_report(result)
    # MANAGED is excluded
    assert report["unmanaged_total"] == 3
    assert len(report["by_tier"]["iot-pool"]) == 2
    assert len(report["by_tier"]["network-gear"]) == 1
    assert "managed" not in report["by_tier"]
