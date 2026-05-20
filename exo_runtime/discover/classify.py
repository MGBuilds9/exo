"""Classify unmanaged LAN devices into tiers.

After Proxmox + inventory cross-reference, anything still unidentified
gets bucketed into network-gear / IoT / end-user / unknown using IP
range heuristics + reverse-DNS patterns + open-port signatures.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .lan import LanDevice


class DeviceTier(str, Enum):
    MANAGED = "managed"           # In inventory; we know what it is
    NETWORK_GEAR = "network-gear" # Switches, APs, gateways
    KEEPALIVED_VIP = "keepalived-vip"  # HA failover VIPs (per Michael's clarification on .29)
    IOT_POOL = "iot-pool"         # DHCP-leased IoT devices
    END_USER = "end-user"         # Laptops, phones, desktops
    NPM_ROUTED = "npm-routed"     # Services routable via NPM but not inventoried
    UNKNOWN = "unknown"


@dataclass
class ClassifiedDevice:
    device: LanDevice
    tier: DeviceTier
    reason: str = ""


# Heuristics
def _classify_one(dev: LanDevice, inventory_ips: set[str],
                  managed_hosts: set[str],
                  npm_routed_ips: set[str]) -> ClassifiedDevice:
    if dev.ip in inventory_ips:
        return ClassifiedDevice(device=dev, tier=DeviceTier.MANAGED,
                                reason="in HOMELAB-INVENTORY.md")
    if dev.ip in managed_hosts:
        return ClassifiedDevice(device=dev, tier=DeviceTier.MANAGED,
                                reason="probed as Proxmox host/workload")
    if dev.ip in npm_routed_ips:
        return ClassifiedDevice(device=dev, tier=DeviceTier.NPM_ROUTED,
                                reason="routed via NPM, not in inventory")
    # Keepalived / HA VIP: hostname matches pi.hole / similar but is duplicate
    if dev.hostname.lower() in {"pi.hole"} and dev.ip not in inventory_ips:
        return ClassifiedDevice(device=dev, tier=DeviceTier.KEEPALIVED_VIP,
                                reason="hostname pi.hole + not unique IP = HA VIP")
    last_octet = int(dev.ip.split(".")[-1])
    # Common network gear octets
    if last_octet in {1, 2, 3} or last_octet in range(11, 18):
        return ClassifiedDevice(device=dev, tier=DeviceTier.NETWORK_GEAR,
                                reason="low octet + typical AP/switch range")
    # Hostname signals for end-user
    h_lower = dev.hostname.lower()
    if any(s in h_lower for s in [".local", "macbook", "iphone", "android",
                                   "windows", "msi", "pc", "laptop", "dgtl",
                                   "mac-", "gg.local"]):
        return ClassifiedDevice(device=dev, tier=DeviceTier.END_USER,
                                reason=f"hostname pattern: {dev.hostname}")
    # DHCP pool — common IoT range
    if 50 <= last_octet <= 120:
        return ClassifiedDevice(device=dev, tier=DeviceTier.IOT_POOL,
                                reason="DHCP pool range .50-.120 (typical IoT)")
    return ClassifiedDevice(device=dev, tier=DeviceTier.UNKNOWN,
                            reason="no classification heuristic matched")


def classify_unmanaged(devices: list[LanDevice],
                       inventory_ips: set[str],
                       managed_hosts: set[str],
                       npm_routed_ips: set[str] | None = None) -> list[ClassifiedDevice]:
    """Classify every device into a tier. Returns sorted by tier."""
    if npm_routed_ips is None:
        npm_routed_ips = set()
    result = [_classify_one(d, inventory_ips, managed_hosts, npm_routed_ips)
              for d in devices]
    tier_order = {t: i for i, t in enumerate([
        DeviceTier.MANAGED, DeviceTier.NPM_ROUTED, DeviceTier.KEEPALIVED_VIP,
        DeviceTier.NETWORK_GEAR, DeviceTier.IOT_POOL, DeviceTier.END_USER,
        DeviceTier.UNKNOWN,
    ])}
    result.sort(key=lambda c: (tier_order.get(c.tier, 99),
                                tuple(int(o) for o in c.device.ip.split("."))))
    return result
