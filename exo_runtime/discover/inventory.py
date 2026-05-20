"""Read an existing HOMELAB-INVENTORY.md (Michael's format) to preserve
manually-curated host metadata across discovery runs.

Format expected: a markdown table under "## Host Status Matrix" with
columns: Host, Status, Type, IP, Parent, Critical, Last Audited.
Lenient parser — tolerates extra columns, varied case.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class InventoryEntry:
    name: str
    ip: str
    type: str = ""             # proxmox-host / lxc / vm / pi / etc.
    parent: str = ""
    status: str = "unknown"    # green / yellow / red / retired / unknown
    last_audited: str = ""
    operational_notes: str = ""


HOST_ROW = re.compile(
    r"^\|\s*\[?([^\]|]+?)\]?(?:\([^)]+\))?\s*\|\s*[^|]*?(\w+)\s*\|\s*([^|]+)\|\s*([0-9.]+)\s*\|\s*([^|]*)\|",
    re.IGNORECASE,
)


def read_inventory(path: Path | str) -> dict[str, InventoryEntry]:
    """Parse HOMELAB-INVENTORY.md into IP-keyed entries. Returns {} if missing."""
    p = Path(path)
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8", errors="replace")
    out: dict[str, InventoryEntry] = {}
    in_matrix = False
    for line in text.splitlines():
        if "Host Status Matrix" in line:
            in_matrix = True
            continue
        if in_matrix and line.startswith("## "):
            break  # next section
        if not in_matrix:
            continue
        m = HOST_ROW.match(line.strip())
        if not m:
            continue
        name, status, host_type, ip, parent = m.groups()
        out[ip.strip()] = InventoryEntry(
            name=name.strip(),
            ip=ip.strip(),
            type=host_type.strip(),
            parent=parent.strip(),
            status=status.strip().lower(),
        )
    return out
