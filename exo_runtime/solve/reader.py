"""Read + parse data sources for exo solve.

Supported source types:
- .html (with embedded `const DATA = {...}` JSON blob — like the homelab map)
- .json (assumed to be a structured object with hosts/nodes/services)
- .yaml/.yml (same)
- .md/.txt (free-form text — issues extracted via regex hints)
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

import yaml


@dataclass
class IssueCandidate:
    """One issue extracted from the data source."""
    id: str
    name: str
    issue_type: str  # critical | degraded | stale | misconfigured | missing | unknown
    severity: int    # 0-10
    description: str
    evidence: list[str] = field(default_factory=list)
    component_type: str = ""   # e.g., proxmox-host, lxc, router, service
    source_path: str = ""      # where in the data we found it
    suggested_fix_hints: list[str] = field(default_factory=list)


@dataclass
class DataDigest:
    """What we extracted from the data source."""
    source_path: str
    source_type: str           # html-data-blob | json | yaml | text
    total_entities: int = 0
    issues: list[IssueCandidate] = field(default_factory=list)
    summary_facts: dict = field(default_factory=dict)


# === HTML parsing (homelab-topology-board.html style) =========================

def _extract_html_data_blob(html: str) -> dict | None:
    """Pull `const DATA = {...};` JSON blob from HTML."""
    m = re.search(r"const\s+DATA\s*=\s*(\{)", html)
    if not m:
        return None
    start = m.end() - 1
    depth = 0
    end = start
    for i, c in enumerate(html[start:], start=start):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    raw = html[start:end]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# Status indicators we recognize in node `liveStatus` / `status` fields
RED_STATUS = {"red", "critical", "down", "🔴", "failed", "broken"}
YELLOW_STATUS = {"yellow", "degraded", "warning", "🟡", "stale", "warn"}


def _issue_from_homelab_node(node: dict, source_path: str) -> IssueCandidate | None:
    """Given a node from a homelab-topology-board, decide if it's an issue."""
    live = (node.get("liveStatus") or node.get("status") or "").lower()
    criticality = (node.get("criticality") or "normal").lower()
    concerns = node.get("concerns") or []
    name = node.get("name") or node.get("id") or "unknown"
    node_id = (node.get("id") or name).replace(".", "-").replace("/", "-").lower()

    severity = 0
    issue_type = "unknown"
    hints: list[str] = []

    if any(r in live for r in RED_STATUS):
        severity = 9
        issue_type = "critical"
        hints.append(f"investigate why {name} is red")
    elif any(y in live for y in YELLOW_STATUS):
        severity = 6
        issue_type = "degraded"
        hints.append(f"check why {name} is degraded before it escalates")
    elif concerns:
        severity = 4
        issue_type = "stale" if any("stale" in str(c).lower() for c in concerns) else "misconfigured"
        hints.append(f"address documented concerns on {name}")

    if criticality in ("critical", "high"):
        severity = min(10, severity + 2)
        hints.append(f"high criticality node — prioritize")

    if severity == 0:
        return None  # healthy, no issue

    desc_parts = []
    if node.get("role"):
        desc_parts.append(node["role"])
    if concerns:
        desc_parts.append(f"Concerns: {'; '.join(str(c) for c in concerns[:3])}")
    evidence = node.get("evidenceLinks", []) or []

    return IssueCandidate(
        id=node_id,
        name=name,
        issue_type=issue_type,
        severity=severity,
        description=" — ".join(desc_parts) if desc_parts else f"{name} is {live or 'unhealthy'}",
        evidence=evidence,
        component_type=node.get("type", ""),
        source_path=source_path,
        suggested_fix_hints=hints,
    )


def _parse_homelab_data(data: dict, source_path: str) -> DataDigest:
    digest = DataDigest(source_path=source_path, source_type="html-data-blob")
    nodes = data.get("nodes", [])
    digest.total_entities = len(nodes)
    for node in nodes:
        if node.get("type") == "unmapped-route-target":
            continue
        issue = _issue_from_homelab_node(node, source_path)
        if issue:
            digest.issues.append(issue)

    summary = data.get("currentSummary", {}) or {}
    counts = data.get("counts", {}) or {}
    digest.summary_facts = {
        "total_hosts": summary.get("total_hosts"),
        "green": summary.get("green"),
        "yellow": summary.get("yellow"),
        "red": summary.get("red"),
        "ai_overall_verdict": summary.get("ai_overall_verdict"),
        "links_count": counts.get("links"),
        "services_count": counts.get("services"),
        "routes_count": counts.get("routes"),
    }
    return digest


# === JSON / YAML parsing ======================================================

def _parse_structured(data: dict | list, source_path: str, source_type: str) -> DataDigest:
    """Best-effort: look for keys named 'nodes', 'hosts', 'issues', 'services', etc."""
    digest = DataDigest(source_path=source_path, source_type=source_type)
    if isinstance(data, list):
        # Treat each list item as a candidate
        for item in data:
            if isinstance(item, dict):
                issue = _issue_from_generic_dict(item, source_path)
                if issue:
                    digest.issues.append(issue)
        digest.total_entities = len(data)
        return digest
    # Dict — look for sub-collections
    for key in ("nodes", "hosts", "items", "services", "issues", "components"):
        if key in data and isinstance(data[key], list):
            for item in data[key]:
                if isinstance(item, dict):
                    issue = _issue_from_generic_dict(item, source_path)
                    if issue:
                        digest.issues.append(issue)
            digest.total_entities = len(data[key])
            break
    digest.summary_facts = {k: v for k, v in data.items() if not isinstance(v, (list, dict))}
    return digest


def _issue_from_generic_dict(item: dict, source_path: str) -> IssueCandidate | None:
    status = (item.get("status") or item.get("liveStatus") or item.get("state") or "").lower()
    severity = item.get("severity")
    name = item.get("name") or item.get("id") or item.get("title") or "unknown"
    if severity is None:
        if any(r in status for r in RED_STATUS): severity = 9
        elif any(y in status for y in YELLOW_STATUS): severity = 6
        else: return None
    try:
        severity = int(severity)
    except (TypeError, ValueError):
        return None
    if severity < 4:
        return None
    return IssueCandidate(
        id=(str(item.get("id") or name)).lower().replace(" ", "-"),
        name=str(name),
        issue_type="critical" if severity >= 8 else "degraded",
        severity=severity,
        description=str(item.get("description") or item.get("notes") or item.get("summary") or "")[:300],
        evidence=item.get("evidenceLinks", []) if isinstance(item.get("evidenceLinks"), list) else [],
        component_type=str(item.get("type") or item.get("kind") or ""),
        source_path=source_path,
        suggested_fix_hints=[],
    )


# === Text parsing =============================================================

def _parse_text(text: str, source_path: str) -> DataDigest:
    """Naive: find lines that mention 'error', 'fail', 'broken', etc."""
    digest = DataDigest(source_path=source_path, source_type="text")
    candidates: list[IssueCandidate] = []
    error_kw = re.compile(r"\b(?:error|fail|fails|failure|broken|down|critical|crash|crashed|unreachable|stale)\b",
                          re.IGNORECASE)
    for i, line in enumerate(text.split("\n"), 1):
        if error_kw.search(line):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "//", "<!--")):
                continue
            candidates.append(IssueCandidate(
                id=f"L{i}",
                name=stripped[:80],
                issue_type="unknown",
                severity=5,
                description=stripped[:300],
                source_path=f"{source_path}:{i}",
            ))
    digest.issues = candidates[:30]  # cap to top 30
    digest.total_entities = len(candidates)
    return digest


# === Public API ================================================================

def read_data_source(path_str: str) -> DataDigest:
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"data source not found: {path}")
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8", errors="replace")

    if suffix == ".html":
        data = _extract_html_data_blob(text)
        if data:
            return _parse_homelab_data(data, str(path))
        return _parse_text(text, str(path))
    if suffix == ".json":
        try:
            data = json.loads(text)
            return _parse_structured(data, str(path), "json")
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON in {path}: {e}")
    if suffix in (".yaml", ".yml"):
        try:
            data = yaml.safe_load(text)
            return _parse_structured(data, str(path), "yaml")
        except yaml.YAMLError as e:
            raise ValueError(f"invalid YAML in {path}: {e}")
    # Fallback: text
    return _parse_text(text, str(path))
