"""Lock the safety-classifier contract.

The execute loop's blast-radius depends on this classifier. If it
misclassifies a destructive command as SAFE in --auto mode, we destroy
something. So every entry here matters.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from exo_runtime.execute.safety import classify_command, SafetyClass, is_runnable_without_explicit_consent


@pytest.mark.parametrize("command", [
    "pvesm status",
    "df -h",
    "free -m",
    "uptime",
    "systemctl status nginx",
    "systemctl --failed",
    "journalctl --no-pager -n 50",
    "journalctl -u sshd --since '1 hour ago'",
    "lsblk",
    "ip a",
    "ip addr",
    "ip r",
    "ip route",
    "ss -tlnp",
    "mount",
    "cat /etc/hosts",
    "ls /var/log",
    "ps aux",
    "docker ps",
    "docker inspect mycontainer",
    "zpool status",
    "zpool list",
    "zfs list",
    "git status",
    "git log --oneline",
    "gh repo view owner/repo",
    "ping -c 3 8.8.8.8",
    "ssh root@host 'pvesm status'",
    "ssh root@host 'free -m'",
])
def test_safe_commands(command):
    assert classify_command(command) == SafetyClass.SAFE, f"expected SAFE for: {command}"


@pytest.mark.parametrize("command", [
    "systemctl restart nginx",
    "systemctl stop postgres",
    "systemctl enable myservice",
    "service nginx restart",
    "pct start 101",
    "pct stop 101",
    "qm start 100",
    "docker restart mycontainer",
    "apt update",
    "pip install requests",
])
def test_caution_commands(command):
    assert classify_command(command) == SafetyClass.CAUTION, f"expected CAUTION for: {command}"


@pytest.mark.parametrize("command", [
    "rm -rf /tmp/foo",
    "rm -r /var/log",
    "dd if=/dev/zero of=/dev/sda",
    "mkfs.ext4 /dev/sdb1",
    "DROP TABLE users",
    "DROP DATABASE production",
    "TRUNCATE TABLE sessions",
    "DELETE FROM users WHERE 1=1",
    "git push --force",
    "git push -f origin main",
    "git reset --hard HEAD~5",
    "git clean -fd",
    "git branch -D feature",
    "docker rm container",
    "docker rmi image",
    "docker volume rm vol",
    "docker system prune",
    "pct destroy 101",
    "qm destroy 100",
    "zfs destroy tank/dataset",
    "zpool destroy tank",
    "apt remove nginx",
    "apt purge mysql",
    "systemctl mask nginx",
])
def test_destructive_commands(command):
    assert classify_command(command) == SafetyClass.DESTRUCTIVE, f"expected DESTRUCTIVE for: {command}"


@pytest.mark.parametrize("command", [
    "some-weird-binary --flag",
    "echo hello | grep world",
    "",
])
def test_unclassified_commands(command):
    assert classify_command(command) == SafetyClass.UNCLASSIFIED, f"expected UNCLASSIFIED for: {command}"


def test_destructive_in_safe_wrapper_still_destructive():
    """Even if wrapped to look safe, rm -rf is still destructive."""
    assert classify_command("ssh root@host 'rm -rf /'") == SafetyClass.DESTRUCTIVE
    assert classify_command("echo skip; rm -rf /tmp/foo") == SafetyClass.DESTRUCTIVE


def test_auto_mode_only_runs_safe():
    """In --auto mode, only SAFE commands run without consent."""
    assert is_runnable_without_explicit_consent("pvesm status") is True
    assert is_runnable_without_explicit_consent("systemctl restart nginx") is False
    assert is_runnable_without_explicit_consent("rm -rf /tmp/foo") is False
    assert is_runnable_without_explicit_consent("echo hi") is False  # unclassified


def test_allow_caution_opens_caution_only():
    """With allow_caution=True, CAUTION commands can auto-run, but not destructive."""
    assert is_runnable_without_explicit_consent("systemctl restart nginx", allow_caution=True) is True
    assert is_runnable_without_explicit_consent("rm -rf /tmp/foo", allow_caution=True) is False
    assert is_runnable_without_explicit_consent("echo hi", allow_caution=True) is False
