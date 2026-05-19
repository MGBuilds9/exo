"""Capability taxonomy loader."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
TAXONOMY_PATH = ROOT / "taxonomy.yaml"


def load_taxonomy() -> dict:
    return yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))


def list_capabilities() -> list[dict]:
    """Returns a flat list of capability dicts with slug populated."""
    tax = load_taxonomy()
    out = []
    for slug, body in tax.get("capabilities", {}).items():
        body = dict(body)
        body["slug"] = slug
        out.append(body)
    return out


def get_capability(slug: str) -> dict | None:
    tax = load_taxonomy()
    body = tax.get("capabilities", {}).get(slug)
    if body is None:
        return None
    body = dict(body)
    body["slug"] = slug
    return body
