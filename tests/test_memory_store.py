"""Lock the memory-store contract — session writes, outcomes, negative results,
and the query helpers that downstream phases (calibration, negative-result
surfacing) depend on.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from exo_runtime.memory.store import MemoryStore, issue_signature


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(tmp_path / "test.db")
    yield s
    s.close()


def _fake_session(session_id="sess-1", issue_name="dgtl-proxmox",
                  signal="storage_inactive", severity=8):
    return {
        "session_id": session_id,
        "plan_source": "/tmp/plan.md",
        "started_at": "2026-05-19T17:00:00+00:00",
        "ended_at": "2026-05-19T17:05:00+00:00",
        "resolution": "completed",
        "summary": "Walked 1 step",
        "steps": [{
            "step_n": 1,
            "timestamp": "2026-05-19T17:00:01+00:00",
            "issue_name": issue_name,
            "proposed_command": "pvesm status",
            "safety_class": "safe",
            "user_decision": "approved",
            "command_result": {"exit_code": 0, "elapsed_seconds": 0.5,
                              "stdout": "...", "stderr": "", "timed_out": False},
            "observed_signals": [
                {"signal": signal, "severity": severity, "detail": "test detail"}
            ],
            "next_step_decision": "investigate further",
            "next_step_command": None,
        }],
    }


def test_schema_initializes(store):
    assert store.session_count() == 0
    assert store.outcome_count() == 0


def test_record_session_roundtrip(store):
    store.record_session(_fake_session())
    assert store.session_count() == 1
    sessions = store.all_sessions()
    assert sessions[0]["session_id"] == "sess-1"
    assert sessions[0]["step_count"] == 1
    assert sessions[0]["resolution"] == "completed"


def test_record_session_idempotent(store):
    """Re-recording the same session_id overwrites cleanly."""
    store.record_session(_fake_session())
    store.record_session(_fake_session())  # same id
    assert store.session_count() == 1


def test_record_outcome_then_query_by_signal(store):
    """The killer query: 'last time we saw signal X, what was the root cause?'"""
    store.record_session(_fake_session(session_id="sess-A",
                                       issue_name="dgtl-proxmox",
                                       signal="storage_inactive"))
    store.record_outcome(
        session_id="sess-A",
        issue_name="dgtl-proxmox",
        component_type="proxmox-host",
        confirmed_root_cause="stale NFS mount on backup-target",
        correct_hypothesis_index=0,
        fix_applied="umount -f -l /mnt/backup; remount",
    )

    priors = store.prior_outcomes_for_signal("storage_inactive")
    assert len(priors) == 1
    assert priors[0]["confirmed_root_cause"] == "stale NFS mount on backup-target"
    assert priors[0]["component_type"] == "proxmox-host"


def test_negative_result_match_by_signature(store):
    """Same issue (name + component + signals) should match same signature."""
    store.record_negative_result(
        issue_name="dgtl-proxmox",
        component_type="proxmox-host",
        top_signals=["storage_inactive", "nfs_stale"],
        what_was_tried="systemctl restart nfs-client",
        why_it_didnt_work="restart finished but mount still stale; needed force-unmount",
    )

    matches = store.tried_and_failed(
        "dgtl-proxmox",
        component_type="proxmox-host",
        top_signals=["nfs_stale", "storage_inactive"],  # different order
    )
    assert len(matches) == 1
    assert "force-unmount" in matches[0]["why_it_didnt_work"]


def test_negative_result_fuzzy_by_name(store):
    """If signature differs but issue_name matches, still surface."""
    store.record_negative_result(
        issue_name="authentik",
        what_was_tried="pct restart 202",
        why_it_didnt_work="container started but service crashed again 30s later",
    )
    # Query with different signals — should still find it
    matches = store.tried_and_failed("authentik", top_signals=["service_crash"])
    assert len(matches) == 1


def test_issue_signature_stable_and_order_invariant():
    a = issue_signature("foo", "lxc", ["x", "y", "z"])
    b = issue_signature("foo", "lxc", ["z", "y", "x"])
    c = issue_signature("foo", "lxc", ["x", "y"])
    assert a == b
    assert a != c


def test_signal_query_empty_when_no_outcome(store):
    """Sessions without recorded outcomes don't pollute the prior-outcome query."""
    store.record_session(_fake_session())
    priors = store.prior_outcomes_for_signal("storage_inactive")
    assert priors == []


def test_session_with_no_steps(store):
    """Edge case: session aborted before any step."""
    empty = _fake_session()
    empty["steps"] = []
    store.record_session(empty)
    assert store.session_count() == 1
    assert store.all_sessions()[0]["step_count"] == 0
