"""exo doctor — scan local hardware + running services + available accounts.

Produces a concrete capability report that `exo architect` consumes to
recommend backends the user *actually has*, not generic defaults.

No external deps beyond stdlib + requests (already a project dep). All
probes have short timeouts (≤2s) and fail gracefully — a missing service
returns False, never raises.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests


# === Data classes ============================================================

@dataclass
class HardwareInfo:
    os: str
    os_release: str
    arch: str
    cpu_cores: int
    ram_total_gb: float
    ram_free_gb: float
    disk_paths: dict          # {drive_or_path: {used_gb, free_gb}}
    gpu_present: bool
    gpu_name: str | None
    gpu_vram_gb: float | None
    gpu_utilization_pct: int | None


@dataclass
class ServiceProbe:
    name: str
    url: str
    reachable: bool
    detail: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class CloudAccount:
    name: str
    env_var: str
    set: bool
    note: str = ""


@dataclass
class DoctorReport:
    timestamp: str
    hardware: HardwareInfo
    services: list[ServiceProbe]
    cloud_accounts: list[CloudAccount]
    summary_lines: list[str]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "hardware": asdict(self.hardware),
            "services": [asdict(s) for s in self.services],
            "cloud_accounts": [asdict(c) for c in self.cloud_accounts],
            "summary_lines": self.summary_lines,
        }


# === Probes ==================================================================

def scan_hardware() -> HardwareInfo:
    os_name = platform.system()
    os_release = platform.version()
    arch = platform.machine()
    cpu_cores = os.cpu_count() or 1

    # RAM via stdlib
    ram_total_gb = 0.0
    ram_free_gb = 0.0
    try:
        if os_name == "Windows":
            # MEMORYSTATUSEX via ctypes
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            ram_total_gb = round(stat.ullTotalPhys / 1024**3, 1)
            ram_free_gb = round(stat.ullAvailPhys / 1024**3, 1)
        else:
            # Linux/macOS via /proc/meminfo or sysconf
            try:
                with open("/proc/meminfo") as f:
                    info = {}
                    for line in f:
                        k, v = line.split(":", 1)
                        info[k] = int(v.split()[0])  # kB
                ram_total_gb = round(info.get("MemTotal", 0) / 1024**2, 1)
                ram_free_gb = round(info.get("MemAvailable", info.get("MemFree", 0)) / 1024**2, 1)
            except FileNotFoundError:
                # macOS fallback via sysctl
                try:
                    out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=3)
                    ram_total_gb = round(int(out.strip()) / 1024**3, 1)
                except Exception:
                    pass
    except Exception:
        pass

    # Disk
    disk_paths = {}
    candidates = ["/", "/home"] if os_name != "Windows" else ["C:\\", "M:\\", "D:\\", "E:\\"]
    for c in candidates:
        try:
            if Path(c).exists():
                usage = shutil.disk_usage(c)
                disk_paths[c] = {
                    "used_gb": round(usage.used / 1024**3, 1),
                    "free_gb": round(usage.free / 1024**3, 1),
                }
        except OSError:
            pass

    # GPU
    gpu_present = False
    gpu_name = None
    gpu_vram_gb = None
    gpu_util = None
    nvidia_smi = shutil.which("nvidia-smi") or shutil.which("nvidia-smi.exe")
    if nvidia_smi:
        try:
            out = subprocess.check_output(
                [nvidia_smi, "--query-gpu=name,memory.total,utilization.gpu", "--format=csv,noheader,nounits"],
                text=True, timeout=4, encoding="utf-8", errors="replace",
            )
            line = out.strip().split("\n")[0]
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                gpu_present = True
                gpu_name = parts[0]
                gpu_vram_gb = round(float(parts[1]) / 1024, 1)
                gpu_util = int(parts[2])
        except Exception:
            pass
    # Windows fallback: wmic — but filter out virtual / display-adapter-only entries
    if not gpu_present and os_name == "Windows":
        try:
            out = subprocess.check_output(
                ["wmic", "path", "win32_VideoController", "get", "name,adapterram", "/format:csv"],
                text=True, timeout=5, encoding="utf-8", errors="replace",
            )
            virtual_keywords = ("virtual", "remote", "rdp", "framebuffer", "sudo", "displaylink", "basic")
            candidates = []
            for line in out.strip().splitlines():
                if line and "Node" not in line and line.count(",") >= 2:
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 3 and parts[2]:
                        name = parts[2]
                        if any(k in name.lower() for k in virtual_keywords):
                            continue
                        try:
                            vram = round(int(parts[1]) / 1024**3, 1) if parts[1] else 0.0
                        except (ValueError, IndexError):
                            vram = 0.0
                        candidates.append((name, vram))
            if candidates:
                # Pick the highest-VRAM candidate
                candidates.sort(key=lambda c: c[1], reverse=True)
                gpu_present = True
                gpu_name = candidates[0][0]
                gpu_vram_gb = candidates[0][1] or None
        except Exception:
            pass

    return HardwareInfo(
        os=os_name, os_release=os_release, arch=arch,
        cpu_cores=cpu_cores,
        ram_total_gb=ram_total_gb, ram_free_gb=ram_free_gb,
        disk_paths=disk_paths,
        gpu_present=gpu_present, gpu_name=gpu_name,
        gpu_vram_gb=gpu_vram_gb, gpu_utilization_pct=gpu_util,
    )


def probe_http(name: str, url: str, expect_json: bool = False, timeout: float = 2.0,
               headers: dict | None = None) -> ServiceProbe:
    try:
        r = requests.get(url, timeout=timeout, headers=headers or {})
        if 200 <= r.status_code < 400:
            detail = {}
            if expect_json:
                try:
                    detail = r.json()
                except json.JSONDecodeError:
                    pass
            return ServiceProbe(name=name, url=url, reachable=True, detail=detail)
        return ServiceProbe(name=name, url=url, reachable=False, error=f"status {r.status_code}")
    except Exception as e:
        return ServiceProbe(name=name, url=url, reachable=False, error=f"{type(e).__name__}: {e}")


def probe_tcp_port(name: str, host: str, port: int, timeout: float = 1.5) -> ServiceProbe:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    url = f"{host}:{port}"
    try:
        s.connect((host, port))
        s.close()
        return ServiceProbe(name=name, url=url, reachable=True, detail={"transport": "tcp"})
    except (TimeoutError, ConnectionRefusedError, OSError) as e:
        return ServiceProbe(name=name, url=url, reachable=False, error=f"{type(e).__name__}")


def probe_cli(name: str, cmd: list[str], timeout: float = 5.0) -> ServiceProbe:
    binary = shutil.which(cmd[0]) or shutil.which(f"{cmd[0]}.cmd") or shutil.which(f"{cmd[0]}.exe")
    if not binary:
        return ServiceProbe(name=name, url=f"binary:{cmd[0]}", reachable=False, error="not in PATH")
    try:
        out = subprocess.check_output([binary, *cmd[1:]], text=True, timeout=timeout,
                                       stderr=subprocess.STDOUT, encoding="utf-8", errors="replace")
        version = out.strip().split("\n")[0][:200]
        return ServiceProbe(name=name, url=binary, reachable=True, detail={"version": version})
    except Exception as e:
        return ServiceProbe(name=name, url=binary, reachable=False, error=f"{type(e).__name__}")


def scan_local_services(extra_hosts: list[str] | None = None) -> list[ServiceProbe]:
    """Probe a curated list of LLM + storage services on localhost and any user-supplied hosts."""
    hosts = ["127.0.0.1"]
    if extra_hosts:
        hosts.extend([h for h in extra_hosts if h])

    probes: list[ServiceProbe] = []

    for host in hosts:
        prefix = "" if host == "127.0.0.1" else f"@{host} "

        # Ollama
        p = probe_http(f"{prefix}Ollama".strip(), f"http://{host}:11434/api/tags", expect_json=True)
        if p.reachable and "models" in p.detail:
            p.detail = {"models": [m.get("name") for m in p.detail.get("models", [])[:20]]}
        probes.append(p)

        # LM Studio / llama-swap (OpenAI-compat on 1234)
        p = probe_http(f"{prefix}LM Studio/llama-swap".strip(), f"http://{host}:1234/v1/models",
                       expect_json=True)
        if p.reachable and "data" in p.detail:
            p.detail = {"models": [m.get("id") for m in p.detail.get("data", [])[:20]]}
        probes.append(p)

        # Qdrant
        probes.append(probe_http(f"{prefix}Qdrant".strip(), f"http://{host}:6333/healthz"))

        # Neo4j (browser)
        probes.append(probe_http(f"{prefix}Neo4j".strip(), f"http://{host}:7474"))

        # Postgres (TCP only — no protocol probe to keep it cheap)
        probes.append(probe_tcp_port(f"{prefix}Postgres".strip(), host, 5432))

        # SearXNG (common port)
        probes.append(probe_http(f"{prefix}SearXNG".strip(), f"http://{host}:8888/healthz"))

    # CLI tools (only on this machine, not over network)
    probes.append(probe_cli("Docker daemon", ["docker", "info", "--format", "{{.ServerVersion}}"]))
    probes.append(probe_cli("Claude Code CLI", ["claude", "--version"]))
    probes.append(probe_cli("Ollama CLI", ["ollama", "--version"]))

    return probes


KNOWN_CLOUD_ACCOUNTS = [
    ("Ollama Cloud", "OLLAMA_API_KEY", "frontier OSS models via API"),
    ("OpenAI", "OPENAI_API_KEY", "GPT-4 / o-series via API (per locked policy: prefer OAuth-Codex over key)"),
    ("Anthropic", "ANTHROPIC_API_KEY", "Claude via API (prefer Claude Code OAuth)"),
    ("Google AI", "GOOGLE_API_KEY", "Gemini via API (prefer gemini-cli OAuth)"),
    ("Cohere", "COHERE_API_KEY", "Command + embeddings"),
    ("Together AI", "TOGETHER_API_KEY", "OSS models via API"),
    ("Replicate", "REPLICATE_API_TOKEN", "Model hosting"),
    ("Hugging Face", "HF_TOKEN", "Inference Endpoints"),
]


def scan_cloud_accounts() -> list[CloudAccount]:
    accounts = []
    for name, env_var, note in KNOWN_CLOUD_ACCOUNTS:
        accounts.append(CloudAccount(
            name=name, env_var=env_var,
            set=bool(os.environ.get(env_var, "").strip()),
            note=note,
        ))
    # Also flag "ALTERNATIVE_NAMES" for OLLAMA
    if not any(c.set for c in accounts if c.name == "Ollama Cloud"):
        alt = os.environ.get("OLLAMA_CLOUD_API_KEY", "").strip()
        if alt:
            for c in accounts:
                if c.name == "Ollama Cloud":
                    c.set = True
                    c.note += " (via OLLAMA_CLOUD_API_KEY)"
    return accounts


# === Summary rendering =======================================================

def build_summary(hw: HardwareInfo, services: list[ServiceProbe],
                  cloud: list[CloudAccount]) -> list[str]:
    lines = []
    lines.append(f"OS: {hw.os} ({hw.os_release.split('.')[0] if hw.os_release else 'unknown'}) on {hw.arch}")
    lines.append(f"CPU: {hw.cpu_cores} cores")
    lines.append(f"RAM: {hw.ram_total_gb} GB total ({hw.ram_free_gb} GB free)")
    disk_str = ", ".join(f"{p}: {d['free_gb']} GB free" for p, d in hw.disk_paths.items())
    lines.append(f"Disk: {disk_str}")
    if hw.gpu_present:
        gpu = f"GPU: {hw.gpu_name}"
        if hw.gpu_vram_gb:
            gpu += f" ({hw.gpu_vram_gb} GB VRAM"
            if hw.gpu_utilization_pct is not None:
                gpu += f", {hw.gpu_utilization_pct}% util"
            gpu += ")"
        lines.append(gpu)
    else:
        lines.append("GPU: none detected (CPU-only inference)")
    lines.append("")
    lines.append("Local services:")
    for p in services:
        marker = "[+]" if p.reachable else "[-]"
        detail_str = ""
        if p.reachable and p.detail:
            if "models" in p.detail:
                models = p.detail["models"]
                detail_str = f" — {len(models)} model(s): {', '.join(models[:5])}{'...' if len(models) > 5 else ''}"
            elif "version" in p.detail:
                detail_str = f" — {p.detail['version']}"
        elif not p.reachable and p.error:
            detail_str = f" — {p.error}"
        lines.append(f"  {marker} {p.name} ({p.url}){detail_str}")
    lines.append("")
    lines.append("Cloud accounts (from environment):")
    for c in cloud:
        marker = "[+]" if c.set else "[-]"
        lines.append(f"  {marker} {c.name} ({c.env_var}){' — ' + c.note if c.set else ''}")
    return lines


def run_doctor(extra_hosts: list[str] | None = None) -> DoctorReport:
    from datetime import datetime, timezone
    hw = scan_hardware()
    services = scan_local_services(extra_hosts=extra_hosts)
    cloud = scan_cloud_accounts()
    summary = build_summary(hw, services, cloud)
    return DoctorReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        hardware=hw, services=services, cloud_accounts=cloud,
        summary_lines=summary,
    )


# === Recommendations consumed by architect ===================================

def recommend_from_doctor(report: DoctorReport, agent_needs: dict | None = None) -> dict:
    """Given a doctor report (and optional agent needs), return concrete recommendations
    naming the user's actual hardware/services."""
    recs = {"primary_llm": None, "fallback_llm": None, "embedding": None,
            "vector_store": None, "graph_store": None, "sql_store": None,
            "hosting_target": None, "notes": []}

    # LLM: prefer Claude OAuth, then Ollama Cloud, then local Ollama, then LM Studio
    claude_ok = any(s.name == "Claude Code CLI" and s.reachable for s in report.services)
    ollama_cloud_ok = any(c.name == "Ollama Cloud" and c.set for c in report.cloud_accounts)
    local_ollama = next((s for s in report.services if s.name == "Ollama" and s.reachable), None)
    lm_studio = next((s for s in report.services if "LM Studio" in s.name and s.reachable), None)

    if claude_ok:
        recs["primary_llm"] = "claude-oauth"
        recs["notes"].append("Claude Code CLI detected — claude-oauth available for frontier-quality actors")
    if ollama_cloud_ok:
        if not recs["primary_llm"]:
            recs["primary_llm"] = "ollama-cloud/qwen3-coder:480b"
        recs["fallback_llm"] = "ollama-cloud/qwen3-coder:480b"
        recs["notes"].append("OLLAMA_API_KEY set — Ollama Cloud frontier-OSS models available")
    if local_ollama:
        models = local_ollama.detail.get("models", [])
        chat_models = [m for m in models if not any(e in m.lower() for e in ("embed", "minilm", "bge"))]
        if chat_models:
            best_local = chat_models[0]  # first; user can override
            if not recs["primary_llm"]:
                recs["primary_llm"] = f"local-ollama/{best_local}"
            if not recs["fallback_llm"]:
                recs["fallback_llm"] = f"local-ollama/{best_local}"
            recs["notes"].append(f"Local Ollama @ :11434 has {len(chat_models)} chat model(s); using {best_local} as local fallback")
        embed_models = [m for m in models if any(e in m.lower() for e in ("embed", "minilm", "bge"))]
        if embed_models:
            recs["embedding"] = f"ollama/{embed_models[0]}"
            recs["notes"].append(f"Local embedding model available: {embed_models[0]}")
    if lm_studio:
        recs["notes"].append(f"LM Studio @ :1234 detected — alternative local inference endpoint")

    # Vector store: prefer Qdrant if running, else Chroma local (lightweight)
    qdrant_local = next((s for s in report.services if "Qdrant" in s.name and s.reachable), None)
    if qdrant_local:
        recs["vector_store"] = "qdrant-local"
        recs["notes"].append(f"Qdrant detected @ {qdrant_local.url} — use as vector backend")
    else:
        recs["vector_store"] = "chroma-embedded"
        recs["notes"].append("No Qdrant detected — recommend Chroma embedded (zero ops)")

    # Graph store
    neo4j_local = next((s for s in report.services if "Neo4j" in s.name and s.reachable), None)
    if neo4j_local:
        recs["graph_store"] = "neo4j-local"
        recs["notes"].append(f"Neo4j detected @ {neo4j_local.url} — graph layer ready")
    else:
        recs["graph_store"] = "lightrag-in-process"
        recs["notes"].append("No Neo4j detected — recommend LightRAG (in-process) if graph tier needed")

    # SQL store
    pg_local = next((s for s in report.services if "Postgres" in s.name and s.reachable), None)
    if pg_local:
        recs["sql_store"] = "postgres-local"
        recs["notes"].append(f"Postgres @ {pg_local.url} — use for structured records")
    else:
        recs["sql_store"] = "sqlite-embedded"
        recs["notes"].append("No Postgres detected — SQLite embedded is fine for personal sims")

    # Hosting: local Docker if present, else just bare Python
    docker_ok = any(s.name == "Docker daemon" and s.reachable for s in report.services)
    if docker_ok:
        recs["hosting_target"] = "local-docker"
    else:
        recs["hosting_target"] = "bare-python"
        recs["notes"].append("Docker not running — runner will operate as bare Python process")

    return recs
