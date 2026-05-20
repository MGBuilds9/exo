"""LAN sweep — ping + reverse DNS + courtesy port scan.

ICMP ping for liveness, reverse DNS for hostname, TCP connect on a small
list of courtesy ports for service identification. NOT a vulnerability
scanner. Read-only / identification only. See docs/PRINCIPLES.md §"What
we deliberately don't do".
"""
from __future__ import annotations

import platform
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field


COURTESY_PORTS = [22, 80, 443, 8006, 8080, 9090, 25, 53]


@dataclass
class LanDevice:
    ip: str
    alive: bool = False
    hostname: str = ""
    open_ports: list[int] = field(default_factory=list)
    notes: str = ""


def _ping(ip: str, timeout_sec: float = 0.5) -> bool:
    """ICMP ping. Cross-platform."""
    is_windows = platform.system().lower().startswith("win")
    if is_windows:
        cmd = ["ping", "-n", "1", "-w", str(int(timeout_sec * 1000)), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(int(timeout_sec) + 1), ip]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout_sec + 1)
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _reverse_dns(ip: str) -> str:
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        return hostname
    except (socket.herror, socket.gaierror, OSError):
        return ""


def _check_port(ip: str, port: int, timeout_sec: float = 0.5) -> bool:
    """TCP connect courtesy probe. No banner, no auth, no payload."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout_sec)
            return s.connect_ex((ip, port)) == 0
    except OSError:
        return False


def _probe_single_ip(ip: str, ports: list[int]) -> LanDevice:
    dev = LanDevice(ip=ip)
    if not _ping(ip):
        return dev
    dev.alive = True
    dev.hostname = _reverse_dns(ip)
    dev.open_ports = [p for p in ports if _check_port(ip, p)]
    return dev


def probe_lan_subnet(subnet_cidr: str = "192.168.0.0/24",
                     courtesy_ports: list[int] | None = None,
                     concurrency: int = 32,
                     verbose: bool = False) -> list[LanDevice]:
    """Sweep a /24 subnet. Returns LanDevice list (alive only)."""
    if courtesy_ports is None:
        courtesy_ports = COURTESY_PORTS
    # Expand /24 to 254 IPs (skip .0 and .255 broadcast)
    base = ".".join(subnet_cidr.split("/")[0].split(".")[:3])
    ips = [f"{base}.{i}" for i in range(1, 255)]

    devices: list[LanDevice] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_probe_single_ip, ip, courtesy_ports): ip for ip in ips}
        for f in as_completed(futures):
            try:
                dev = f.result()
                if dev.alive:
                    devices.append(dev)
                    if verbose:
                        ports_str = ",".join(str(p) for p in dev.open_ports) or "-"
                        print(f"    {dev.ip:15s} {dev.hostname[:30]:30s} ports={ports_str}")
            except Exception:
                pass
    devices.sort(key=lambda d: tuple(int(o) for o in d.ip.split(".")))
    return devices
