"""End-to-end test of the execute action loop using replayed command output.

This is what `exo execute --replay <fixture.yaml>` exercises: planner reads a
plan, runs the proposed commands via the ReplayRunner instead of subprocess,
parser turns synthetic stdout into signals, the next-step decision is made,
the session is persisted, memory is updated. No infra touched.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import yaml

from exo_runtime.execute.replay import (
    load_fixture, ReplayRunner, ReplayFixture, ReplayResponse,
)
from exo_runtime.execute.parser import parse_output


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "execute-replays"


def test_fixture_loads():
    fix = load_fixture(FIXTURE_DIR / "proxmox-storage-inactive.yaml")
    assert "stale NFS" in fix.description
    assert len(fix.responses) == 4


def test_replay_returns_synthetic_output():
    fix = load_fixture(FIXTURE_DIR / "proxmox-storage-inactive.yaml")
    runner = ReplayRunner(fix)
    result = runner("ssh root@dgtl 'pvesm status'")
    assert result.exit_code == 0
    assert "local-zfs" in result.stdout
    assert "inactive" in result.stdout


def test_replay_miss_is_loud():
    """A command not in the fixture should return exit 127 with a clear stderr."""
    fix = load_fixture(FIXTURE_DIR / "proxmox-storage-inactive.yaml")
    runner = ReplayRunner(fix)
    result = runner("unknown-command --no-such-flag")
    assert result.exit_code == 127
    assert "no fixture response matched" in result.stderr


def test_replay_then_parse_to_signals():
    """The whole point: replayed output → parser → signals."""
    fix = load_fixture(FIXTURE_DIR / "proxmox-storage-inactive.yaml")
    runner = ReplayRunner(fix)
    result = runner("pvesm status")
    signals = parse_output("pvesm status", result.stdout, result.stderr, result.exit_code)
    # Should detect the inactive storage
    names = [s.signal for s in signals]
    assert "storage_inactive" in names
    inactive = [s for s in signals if s.signal == "storage_inactive"][0]
    assert "local-zfs" in inactive.detail


def test_replay_tracks_unused_responses():
    """Fixtures should tell us when responses are never used — dead code in tests."""
    fix = ReplayFixture(
        description="trivial",
        responses=[
            ReplayResponse(command_regex="^foo", stdout="bar"),
            ReplayResponse(command_regex="^baz", stdout="qux"),
        ],
    )
    runner = ReplayRunner(fix)
    runner("foo --version")
    unused = fix.unused()
    assert len(unused) == 1
    assert unused[0].command_regex == "^baz"


def test_replay_mount_detects_stale_nfs():
    """Verify mount parsing extracts the stale NFS signal."""
    fix = load_fixture(FIXTURE_DIR / "proxmox-storage-inactive.yaml")
    runner = ReplayRunner(fix)
    result = runner("mount | grep nfs")
    signals = parse_output("mount | grep nfs", result.stdout, "", 0)
    names = [s.signal for s in signals]
    assert "nfs_stale" in names


def test_replay_systemctl_failed():
    fix = load_fixture(FIXTURE_DIR / "proxmox-storage-inactive.yaml")
    runner = ReplayRunner(fix)
    result = runner("systemctl --failed")
    signals = parse_output("systemctl --failed", result.stdout, "", 0)
    names = [s.signal for s in signals]
    assert "failed_units" in names


def test_replay_df_healthy():
    """The fixture's df shows everything healthy."""
    fix = load_fixture(FIXTURE_DIR / "proxmox-storage-inactive.yaml")
    runner = ReplayRunner(fix)
    result = runner("df -h")
    signals = parse_output("df -h", result.stdout, "", 0)
    names = [s.signal for s in signals]
    assert "disk_healthy" in names


def test_full_chain_via_cli(tmp_path, monkeypatch):
    """End-to-end: write a tiny plan, run exo execute --replay, verify session JSON."""
    monkeypatch.setenv("EXO_HOME", str(tmp_path / "exo-home"))

    plan_md = tmp_path / "plan.md"
    plan_md.write_text("""# tiny plan

## 1. dgtl-proxmox (critical, severity 10)

- **Component type:** proxmox-host

### Diagnosis
Proxmox host critical.

### Hypotheses (ranked cheapest-first)
- Backup-target mount has gone stale
- Lost NFS share / drift

### First action (needs your consent)
**Step:** Probe storage.
```
ssh root@dgtl-proxmox 'pvesm status'
```
**Verification:** look for inactive.

### Clarifying questions before I propose more
- Anything?

---
""")

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from cli import execute_cmd
    execute_cmd.run(
        plan_path=str(plan_md),
        out_dir=str(tmp_path / "out"),
        auto=True,
        allow_caution=False,
        max_steps=1,
        replay_fixture=str(FIXTURE_DIR / "proxmox-storage-inactive.yaml"),
    )

    # Session JSON should exist and contain the storage_inactive signal
    import json
    out_files = list((tmp_path / "out").glob("*.json"))
    assert len(out_files) == 1
    session = json.loads(out_files[0].read_text(encoding="utf-8"))
    assert session["resolution"] == "completed"
    step = session["steps"][0]
    signals = [s["signal"] for s in step["observed_signals"]]
    assert "storage_inactive" in signals
    # And it should have proposed a follow-up
    assert step["next_step_decision"] != ""
