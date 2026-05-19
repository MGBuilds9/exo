"""Persistent memory for exo — sessions, outcomes, negative results.

Lives in SQLite at ~/.exo/sessions.db. Foundation for:
- recall ("we hit this signal before; here's what was true")
- calibration ("planner is well-tuned on proxmox, weak on lxc")
- negative results ("we already tried this and it didn't work")
"""
from .store import (
    MemoryStore, default_store_path,
    record_session, record_outcome, record_negative_result,
    prior_outcomes_for_signal, tried_and_failed,
)

__all__ = [
    "MemoryStore", "default_store_path",
    "record_session", "record_outcome", "record_negative_result",
    "prior_outcomes_for_signal", "tried_and_failed",
]
