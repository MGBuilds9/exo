"""SQLite-backed memory store for exo sessions, outcomes, negative results.

Design choices:
- One DB per user at ~/.exo/sessions.db. No sharing yet (Phase B / opt-in corpus
  is a future concern).
- All writes are idempotent on session_id — re-recording the same session
  overwrites (so a session that ends with `--abort` can still be saved).
- No ORM. Plain sqlite3 + raw SQL. The schema is small enough that an ORM
  would be overhead.
- Schema version stored in `pragma_meta` table; future migrations key off it.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS pragma_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    plan_source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    resolution TEXT NOT NULL,
    summary TEXT,
    step_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS steps (
    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    step_n INTEGER NOT NULL,
    issue_name TEXT NOT NULL,
    proposed_command TEXT NOT NULL,
    safety_class TEXT NOT NULL,
    user_decision TEXT NOT NULL,
    exit_code INTEGER,
    elapsed_seconds REAL,
    timestamp TEXT NOT NULL,
    next_step_decision TEXT,
    UNIQUE(session_id, step_n)
);

CREATE TABLE IF NOT EXISTS observed_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    step_id INTEGER NOT NULL REFERENCES steps(step_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    issue_name TEXT NOT NULL,
    signal TEXT NOT NULL,
    severity INTEGER NOT NULL,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS outcomes (
    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    issue_name TEXT NOT NULL,
    component_type TEXT,
    confirmed_root_cause TEXT NOT NULL,
    correct_hypothesis_index INTEGER,
    fix_applied TEXT,
    ground_truth_source TEXT DEFAULT 'user',
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS negative_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_signature TEXT NOT NULL,
    issue_name TEXT NOT NULL,
    component_type TEXT,
    what_was_tried TEXT NOT NULL,
    why_it_didnt_work TEXT,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signals_signal ON observed_signals(signal);
CREATE INDEX IF NOT EXISTS idx_outcomes_issue ON outcomes(issue_name);
CREATE INDEX IF NOT EXISTS idx_outcomes_component ON outcomes(component_type);
CREATE INDEX IF NOT EXISTS idx_negresults_signature ON negative_results(issue_signature);
"""


def default_store_path() -> Path:
    """Default location of the user's memory DB. Override via $EXO_HOME."""
    base = Path(os.environ.get("EXO_HOME") or (Path.home() / ".exo"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "sessions.db"


def issue_signature(issue_name: str, component_type: Optional[str],
                    top_signals: Iterable[str] = ()) -> str:
    """Stable signature for an issue — used to match negative-results across sessions."""
    parts = [issue_name.strip().lower(), (component_type or "").strip().lower()]
    parts.extend(sorted(s.strip().lower() for s in top_signals))
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return h[:16]


# === Core store ==============================================================

class MemoryStore:
    """Thin wrapper around sqlite3 with the exo schema applied."""

    def __init__(self, path: Optional[Path | str] = None):
        self.path = Path(path) if path else default_store_path()
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def _migrate(self) -> None:
        self.conn.executescript(DDL)
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO pragma_meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- session writes -------------------------------------------------

    def record_session(self, session_dict: dict) -> str:
        """Write a session (ExecuteSession.asdict()-shaped) idempotently."""
        sid = session_dict["session_id"]
        # delete-then-insert is simplest for idempotent overwrite
        self.conn.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))
        self.conn.execute("""
            INSERT INTO sessions(session_id, plan_source, started_at, ended_at,
                                 resolution, summary, step_count)
            VALUES(?,?,?,?,?,?,?)
        """, (
            sid, session_dict.get("plan_source", ""),
            session_dict.get("started_at", ""),
            session_dict.get("ended_at"),
            session_dict.get("resolution", "in_progress"),
            session_dict.get("summary", ""),
            len(session_dict.get("steps", [])),
        ))

        for step in session_dict.get("steps", []):
            cur = self.conn.execute("""
                INSERT INTO steps(session_id, step_n, issue_name, proposed_command,
                                  safety_class, user_decision, exit_code,
                                  elapsed_seconds, timestamp, next_step_decision)
                VALUES(?,?,?,?,?,?,?,?,?,?)
            """, (
                sid, step["step_n"], step["issue_name"], step["proposed_command"],
                step["safety_class"], step["user_decision"],
                (step.get("command_result") or {}).get("exit_code"),
                (step.get("command_result") or {}).get("elapsed_seconds"),
                step["timestamp"],
                step.get("next_step_decision", ""),
            ))
            step_id = cur.lastrowid
            for sig in step.get("observed_signals", []):
                self.conn.execute("""
                    INSERT INTO observed_signals(step_id, session_id, issue_name,
                                                 signal, severity, detail)
                    VALUES(?,?,?,?,?,?)
                """, (
                    step_id, sid, step["issue_name"],
                    sig.get("signal", "unknown"),
                    int(sig.get("severity", 0)),
                    sig.get("detail", ""),
                ))
        self.conn.commit()
        return sid

    def record_outcome(self, session_id: str, issue_name: str,
                       confirmed_root_cause: str,
                       component_type: Optional[str] = None,
                       correct_hypothesis_index: Optional[int] = None,
                       fix_applied: Optional[str] = None,
                       ground_truth_source: str = "user") -> int:
        cur = self.conn.execute("""
            INSERT INTO outcomes(session_id, issue_name, component_type,
                                 confirmed_root_cause, correct_hypothesis_index,
                                 fix_applied, ground_truth_source, recorded_at)
            VALUES(?,?,?,?,?,?,?,?)
        """, (
            session_id, issue_name, component_type, confirmed_root_cause,
            correct_hypothesis_index, fix_applied, ground_truth_source,
            datetime.now(timezone.utc).isoformat(),
        ))
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def record_negative_result(self, issue_name: str, what_was_tried: str,
                                why_it_didnt_work: Optional[str] = None,
                                component_type: Optional[str] = None,
                                top_signals: Iterable[str] = ()) -> int:
        sig = issue_signature(issue_name, component_type, top_signals)
        cur = self.conn.execute("""
            INSERT INTO negative_results(issue_signature, issue_name, component_type,
                                         what_was_tried, why_it_didnt_work,
                                         recorded_at)
            VALUES(?,?,?,?,?,?)
        """, (
            sig, issue_name, component_type, what_was_tried, why_it_didnt_work,
            datetime.now(timezone.utc).isoformat(),
        ))
        self.conn.commit()
        return int(cur.lastrowid or 0)

    # --- queries --------------------------------------------------------

    def prior_outcomes_for_signal(self, signal: str, limit: int = 10) -> list[dict]:
        """For a given observed signal, what was the actual root cause last time(s)?"""
        rows = self.conn.execute("""
            SELECT DISTINCT o.outcome_id, o.issue_name, o.component_type,
                   o.confirmed_root_cause, o.fix_applied, o.recorded_at
            FROM observed_signals s
            JOIN outcomes o
              ON o.session_id = s.session_id
             AND o.issue_name = s.issue_name
            WHERE s.signal = ?
            ORDER BY o.recorded_at DESC
            LIMIT ?
        """, (signal, limit)).fetchall()
        return [dict(r) for r in rows]

    def tried_and_failed(self, issue_name: str,
                         component_type: Optional[str] = None,
                         top_signals: Iterable[str] = (),
                         limit: int = 20) -> list[dict]:
        """Negative results matching this issue signature."""
        sig = issue_signature(issue_name, component_type, top_signals)
        # Match on signature first; also fuzzy-match same issue_name
        rows = self.conn.execute("""
            SELECT id, issue_name, component_type, what_was_tried,
                   why_it_didnt_work, recorded_at
            FROM negative_results
            WHERE issue_signature = ? OR issue_name = ?
            ORDER BY recorded_at DESC
            LIMIT ?
        """, (sig, issue_name, limit)).fetchall()
        return [dict(r) for r in rows]

    def session_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])

    def outcome_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0])

    def all_sessions(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute("""
            SELECT session_id, plan_source, started_at, ended_at, resolution,
                   summary, step_count
            FROM sessions
            ORDER BY started_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


# === Module-level convenience helpers ========================================

def record_session(session_dict: dict, store: Optional[MemoryStore] = None) -> str:
    own = store is None
    s = store or MemoryStore()
    try:
        return s.record_session(session_dict)
    finally:
        if own:
            s.close()


def record_outcome(session_id: str, issue_name: str, confirmed_root_cause: str,
                   store: Optional[MemoryStore] = None, **kwargs) -> int:
    own = store is None
    s = store or MemoryStore()
    try:
        return s.record_outcome(session_id, issue_name, confirmed_root_cause, **kwargs)
    finally:
        if own:
            s.close()


def record_negative_result(issue_name: str, what_was_tried: str,
                            store: Optional[MemoryStore] = None, **kwargs) -> int:
    own = store is None
    s = store or MemoryStore()
    try:
        return s.record_negative_result(issue_name, what_was_tried, **kwargs)
    finally:
        if own:
            s.close()


def prior_outcomes_for_signal(signal: str, limit: int = 10,
                               store: Optional[MemoryStore] = None) -> list[dict]:
    own = store is None
    s = store or MemoryStore()
    try:
        return s.prior_outcomes_for_signal(signal, limit=limit)
    finally:
        if own:
            s.close()


def tried_and_failed(issue_name: str, component_type: Optional[str] = None,
                     top_signals: Iterable[str] = (),
                     limit: int = 20,
                     store: Optional[MemoryStore] = None) -> list[dict]:
    own = store is None
    s = store or MemoryStore()
    try:
        return s.tried_and_failed(issue_name, component_type=component_type,
                                  top_signals=top_signals, limit=limit)
    finally:
        if own:
            s.close()
