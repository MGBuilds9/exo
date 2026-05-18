"""Extract signal JSON from actor responses.

Convention: actor responses end with a line `___SIGNALS___ {"name": value, ...}`.
This module strips that line out of the displayed content and returns the parsed dict.
"""
from __future__ import annotations

import json
import re


SIGNAL_RE = re.compile(r"___SIGNALS___\s*({[^{}]*})", re.DOTALL)


def extract_signals(text: str, expected: list[str]) -> tuple[str, dict]:
    """Returns (content_without_signal_line, parsed_signals_dict).

    Robust to:
    - Missing signal line (returns text unchanged, signals = {})
    - Malformed JSON (returns text with signal line stripped, signals = {})
    - Extra signals (filtered to `expected` only)
    """
    match = SIGNAL_RE.search(text)
    if not match:
        return text.strip(), {}

    raw_json = match.group(1)
    content = SIGNAL_RE.sub("", text).strip()

    try:
        parsed = json.loads(raw_json)
        if not isinstance(parsed, dict):
            return content, {}
        if expected:
            parsed = {k: v for k, v in parsed.items() if k in expected}
        # Coerce values to float where possible
        coerced = {}
        for k, v in parsed.items():
            try:
                coerced[k] = float(v)
            except (TypeError, ValueError):
                coerced[k] = v
        return content, coerced
    except json.JSONDecodeError:
        return content, {}
