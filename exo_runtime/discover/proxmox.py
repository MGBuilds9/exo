"""SSH-driven Proxmox discovery.

Uses `pvesh get /cluster/resources --output-format json` to enumerate all
hosts + LXCs + VMs, then `pct config <id>` / `qm config <id>` to extract
RAM allocation, CPU threads, GPU passthrough, and other workload metadata.

Falls back gracefully if any one host is unreachable. Network bandwidth +
topology mapping (the next gap) lives in a separate module.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProxmoxHost:
    name: str
    ip: str
    cpu_threads: int = 0
    ram_mb: int = 0
    has_gpu: bool = False
    gpu_model: str = ""
    role_hint: str = ""
    notes: str = ""
    audit_status: str = "unknown"      # green/yellow/red/unknown
    error: Optional[str] = None


@dataclass
class ProxmoxWorkload:
    name: str
    workload_id: str
    workload_type: str               # "lxc" / "vm"
    current_host: str
    ram_mb: int = 1024
    cpu_threads: int = 1
    disk_gb: int = 8
    needs_gpu: bool = False
    pin_to_host: Optional[str] = None
    tier: str = "user"
    notes: str = ""


# Heuristic: workload name → needs GPU (tunable). Matches Michael's homelab pattern.
GPU_NAME_HINTS = {"openclaw", "forge-knowledge", "langgraph", "blender", "ollama", "vllm", "comfyui", "automatic1111"}

# Heuristic: workload name → tier classification
COMPUTE_HINTS = {"openclaw", "forge-knowledge", "langgraph", "blender", "ollama", "tools-debian", "hoppscotch", "lwp"}
STORAGE_HINTS = {"truenas", "minio", "nextcloud", "syncthing", "samba"}
EDGE_HINTS = {"homeassistant", "homebridge", "frigate", "netbird", "tailscale", "coolify"}
USER_TIER_HINTS = {"authentik", "nginxproxymanager", "npm", "adguard", "pihole", "drawio", "automation", "media", "camofox", "pascal-editor", "david-productivity", "simplefin"}


def _ssh(host: str, cmd: str, timeout: int = 30, ssh_user: str = "root") -> tuple[int, str, str]:
    """Run cmd on host via SSH. Returns (exit_code, stdout, stderr)."""
    ssh_bin = shutil.which("ssh")
    if not ssh_bin:
        return (-1, "", "ssh binary not found in PATH")
    try:
        proc = subprocess.run(
            [ssh_bin, "-o", "StrictHostKeyChecking=accept-new",
             "-o", f"ConnectTimeout={min(timeout, 10)}",
             f"{ssh_user}@{host}", cmd],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return (proc.returncode, proc.stdout or "", proc.stderr or "")
    except subprocess.TimeoutExpired:
        return (-1, "", f"timeout after {timeout}s")
    except Exception as e:
        return (-1, "", str(e))


def _classify_tier(name: str, has_gpu_hint: bool) -> str:
    """Guess tier from workload name."""
    n = name.lower()
    if any(h in n for h in STORAGE_HINTS):
        return "storage"
    if any(h in n for h in EDGE_HINTS):
        return "edge"
    if has_gpu_hint or any(h in n for h in COMPUTE_HINTS):
        return "compute"
    if any(h in n for h in USER_TIER_HINTS):
        return "user"
    return "user"   # default


def _needs_gpu(name: str) -> bool:
    n = name.lower()
    return any(h in n for h in GPU_NAME_HINTS)


def _parse_pct_config(config_text: str) -> dict:
    """Parse `pct config <id>` output (key: value lines)."""
    out = {}
    for line in config_text.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip().lower()] = v.strip()
    return out


def _ram_from_config(cfg: dict) -> int:
    """Extract RAM in MB from a pct/qm config dict."""
    # pct: 'memory: 4096', qm: 'memory: 4096'
    mem = cfg.get("memory", "")
    if mem.isdigit():
        return int(mem)
    return 1024  # safe default


def _cpu_from_config(cfg: dict, workload_type: str) -> int:
    """Extract CPU thread count from config."""
    if workload_type == "lxc":
        return int(cfg.get("cores", "1") or 1)
    # vm
    cores = int(cfg.get("cores", "1") or 1)
    sockets = int(cfg.get("sockets", "1") or 1)
    return cores * sockets


def _gpu_passthrough_in_config(cfg: dict) -> bool:
    """Detect GPU pass-through in config (hostpci, vGPU, NVIDIA, etc.)."""
    for key, val in cfg.items():
        if key.startswith("hostpci"):
            return True
        if "nvidia" in val.lower() or "vendor=10de" in val.lower():
            return True
    return False


def probe_proxmox_cluster(seed_hosts: list[str],
                          ssh_user: str = "root",
                          verbose: bool = False) -> tuple[list[ProxmoxHost], list[ProxmoxWorkload]]:
    """Discover all Proxmox hosts + their workloads, starting from seed IPs.

    For each seed host, queries /cluster/resources to enumerate the whole
    cluster (if the seed is part of a cluster) — handles single-host setups
    via fallback to /nodes/<self>/...
    """
    hosts: dict[str, ProxmoxHost] = {}
    workloads: list[ProxmoxWorkload] = []

    for seed in seed_hosts:
        if verbose:
            print(f"  probing {seed} via SSH...")
        # First try cluster resources (works on clustered setups)
        rc, stdout, stderr = _ssh(seed, "pvesh get /cluster/resources --output-format json",
                                   ssh_user=ssh_user)
        resources = []
        if rc == 0:
            try:
                resources = json.loads(stdout)
            except json.JSONDecodeError:
                if verbose:
                    print(f"    cluster resources JSON parse failed; falling back to /nodes")
        if not resources:
            # Single-host fallback
            rc, stdout, _ = _ssh(seed, "pvesh get /nodes --output-format json", ssh_user=ssh_user)
            if rc == 0:
                try:
                    nodes = json.loads(stdout)
                    resources = [{"type": "node", **n} for n in nodes]
                except json.JSONDecodeError:
                    pass

        # Process resources
        for r in resources:
            rtype = r.get("type")
            if rtype == "node":
                node_name = r.get("node") or r.get("name", seed)
                # Pull node hardware spec
                rc, hw_stdout, _ = _ssh(seed, f"pvesh get /nodes/{node_name}/status --output-format json",
                                         ssh_user=ssh_user)
                cpu_threads, ram_mb = 0, 0
                if rc == 0:
                    try:
                        status = json.loads(hw_stdout)
                        cpu_threads = int(status.get("cpuinfo", {}).get("cpus", 0))
                        ram_mb = int(status.get("memory", {}).get("total", 0)) // (1024 * 1024)
                    except (json.JSONDecodeError, AttributeError, TypeError):
                        pass
                # GPU detection via lspci
                rc, lspci_stdout, _ = _ssh(seed, "lspci | grep -i 'vga\\|3d\\|display' | head -1",
                                            ssh_user=ssh_user)
                has_gpu = False
                gpu_model = ""
                if rc == 0 and lspci_stdout.strip():
                    has_gpu = True
                    gpu_model = lspci_stdout.strip().split(":")[-1].strip()[:60]
                if node_name not in hosts:
                    hosts[node_name] = ProxmoxHost(
                        name=node_name, ip=seed,
                        cpu_threads=cpu_threads, ram_mb=ram_mb,
                        has_gpu=has_gpu, gpu_model=gpu_model,
                    )
            elif rtype in ("lxc", "qemu"):
                vmid = str(r.get("vmid", ""))
                w_name = r.get("name", f"workload-{vmid}")
                w_type = "lxc" if rtype == "lxc" else "vm"
                w_host = r.get("node", seed)
                config_cmd = ("pct" if w_type == "lxc" else "qm") + f" config {vmid}"
                rc, cfg_stdout, _ = _ssh(seed, config_cmd, ssh_user=ssh_user)
                cfg = _parse_pct_config(cfg_stdout) if rc == 0 else {}
                ram_mb = _ram_from_config(cfg) if cfg else 1024
                cpu_threads = _cpu_from_config(cfg, w_type) if cfg else 1
                gpu_passthrough = _gpu_passthrough_in_config(cfg) if cfg else False
                needs_gpu = gpu_passthrough or _needs_gpu(w_name)
                tier = _classify_tier(w_name, needs_gpu)
                workloads.append(ProxmoxWorkload(
                    name=w_name, workload_id=vmid, workload_type=w_type,
                    current_host=w_host, ram_mb=ram_mb, cpu_threads=cpu_threads,
                    needs_gpu=needs_gpu, tier=tier,
                    notes=cfg.get("description", "")[:120],
                ))

        if verbose and resources:
            print(f"    {seed}: {sum(1 for r in resources if r.get('type') == 'node')} node(s), "
                  f"{sum(1 for r in resources if r.get('type') in ('lxc','qemu'))} workload(s)")

    # Dedupe workloads (in case a clustered seed returned overlap)
    seen_ids: set[tuple[str, str]] = set()
    deduped_workloads = []
    for w in workloads:
        key = (w.workload_id, w.current_host)
        if key in seen_ids:
            continue
        seen_ids.add(key)
        deduped_workloads.append(w)

    return list(hosts.values()), deduped_workloads
