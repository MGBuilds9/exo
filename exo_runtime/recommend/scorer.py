"""Score a candidate repo against trust + maintenance + fit signals.

All signals come from live GitHub API via the `gh` CLI. No LLM in the
scoring path — deterministic, auditable, reproducible.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass
class RepoSignals:
    """Raw signals pulled from GitHub for one repo."""
    full_name: str
    stars: int = 0
    forks: int = 0
    watchers: int = 0
    open_issues: int = 0
    created_at: str | None = None
    pushed_at: str | None = None
    license_key: str | None = None
    language: str | None = None
    archived: bool = False
    disabled: bool = False
    fork: bool = False
    contributor_count: int = 0
    recent_commit_count_90d: int = 0
    recent_release_count_90d: int = 0
    description: str = ""
    homepage: str = ""
    fetch_error: str | None = None


@dataclass
class RepoScore:
    """Score breakdown for one repo."""
    full_name: str
    signals: RepoSignals
    maintenance: float = 0.0          # 0-10
    popularity: float = 0.0            # 0-10
    governance: float = 0.0            # 0-10
    license_fit: float = 0.0           # 0-10
    composite: float = 0.0             # 0-10 weighted
    rationale: list[str] = field(default_factory=list)


# === GitHub data fetch (via gh CLI) ===========================================

def _gh(args: list[str], timeout: int = 30) -> str | None:
    """Run gh CLI. Returns stdout str or None on error."""
    binary = shutil.which("gh") or shutil.which("gh.exe")
    if not binary:
        return None
    try:
        proc = subprocess.run(
            [binary, *args],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        if proc.returncode != 0:
            return None
        return proc.stdout
    except Exception:
        return None


def fetch_repo_signals(full_name: str) -> RepoSignals:
    """Pull live signals for one repo via gh CLI."""
    sig = RepoSignals(full_name=full_name)

    # Core repo metadata
    out = _gh(["api", f"/repos/{full_name}",
               "--jq",
               "{stars:.stargazers_count, forks:.forks_count, watchers:.watchers_count, "
               "open_issues:.open_issues_count, created_at:.created_at, pushed_at:.pushed_at, "
               "license_key:.license.key, language:.language, archived:.archived, "
               "disabled:.disabled, fork:.fork, description:.description, homepage:.homepage}"])
    if not out:
        sig.fetch_error = f"could not fetch /repos/{full_name}"
        return sig
    try:
        meta = json.loads(out)
    except json.JSONDecodeError:
        sig.fetch_error = "metadata parse error"
        return sig

    for k, v in meta.items():
        if hasattr(sig, k) and v is not None:
            setattr(sig, k, v)

    # Contributors (anon=false; cap at 100 page so we don't spend rate-limit on huge repos)
    out = _gh(["api", f"/repos/{full_name}/contributors?per_page=100&anon=0", "--jq", "length"])
    if out:
        try:
            sig.contributor_count = int(out.strip())
        except (ValueError, TypeError):
            pass

    # Recent commits (last 90 days)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = _gh(["api", f"/repos/{full_name}/commits?since={cutoff}&per_page=100", "--jq", "length"])
    if out:
        try:
            sig.recent_commit_count_90d = int(out.strip())
        except (ValueError, TypeError):
            pass

    # Recent releases (last 90 days; we count any release whose published_at >= cutoff)
    out = _gh(["api", f"/repos/{full_name}/releases?per_page=100",
               "--jq", f'[.[] | select(.published_at >= "{cutoff}")] | length'])
    if out:
        try:
            sig.recent_release_count_90d = int(out.strip())
        except (ValueError, TypeError):
            pass

    return sig


# === Scoring ==================================================================

def _days_since(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    except (ValueError, TypeError):
        return None


def _stars_per_day(sig: RepoSignals) -> float | None:
    age = _days_since(sig.created_at)
    if not age or age < 1:
        return None
    return sig.stars / age


def _score_maintenance(sig: RepoSignals, rationale: list[str]) -> float:
    """0-10. Based on commit recency + release cadence + activity volume."""
    score = 0.0
    days_since_push = _days_since(sig.pushed_at)
    if days_since_push is None:
        rationale.append("maintenance: no push date → 3.0 (uncertain)")
        return 3.0
    if days_since_push < 7:
        score += 4.0
        rationale.append(f"maintenance: pushed {days_since_push:.0f}d ago → +4.0")
    elif days_since_push < 30:
        score += 3.0
        rationale.append(f"maintenance: pushed {days_since_push:.0f}d ago → +3.0")
    elif days_since_push < 90:
        score += 2.0
        rationale.append(f"maintenance: pushed {days_since_push:.0f}d ago → +2.0")
    elif days_since_push < 180:
        score += 1.0
        rationale.append(f"maintenance: pushed {days_since_push:.0f}d ago → +1.0")
    else:
        rationale.append(f"maintenance: stale ({days_since_push:.0f}d) → +0.0")

    if sig.recent_commit_count_90d >= 50:
        score += 3.0
        rationale.append(f"maintenance: {sig.recent_commit_count_90d} commits in 90d → +3.0")
    elif sig.recent_commit_count_90d >= 20:
        score += 2.0
        rationale.append(f"maintenance: {sig.recent_commit_count_90d} commits in 90d → +2.0")
    elif sig.recent_commit_count_90d >= 5:
        score += 1.0
        rationale.append(f"maintenance: {sig.recent_commit_count_90d} commits in 90d → +1.0")

    if sig.recent_release_count_90d >= 3:
        score += 3.0
        rationale.append(f"maintenance: {sig.recent_release_count_90d} releases in 90d → +3.0")
    elif sig.recent_release_count_90d >= 1:
        score += 2.0
        rationale.append(f"maintenance: {sig.recent_release_count_90d} releases in 90d → +2.0")

    if sig.archived:
        rationale.append("maintenance: ARCHIVED → -8.0")
        score -= 8.0
    if sig.disabled:
        rationale.append("maintenance: DISABLED → -10.0")
        score -= 10.0

    return max(0.0, min(10.0, score))


def _score_popularity(sig: RepoSignals, rationale: list[str]) -> float:
    """0-10. Based on stars + stars-per-day."""
    score = 0.0
    if sig.stars >= 50000: score = 10.0; rationale.append(f"popularity: {sig.stars} stars → 10")
    elif sig.stars >= 20000: score = 9.0; rationale.append(f"popularity: {sig.stars} stars → 9")
    elif sig.stars >= 10000: score = 8.0; rationale.append(f"popularity: {sig.stars} stars → 8")
    elif sig.stars >= 5000: score = 7.0; rationale.append(f"popularity: {sig.stars} stars → 7")
    elif sig.stars >= 2000: score = 6.0; rationale.append(f"popularity: {sig.stars} stars → 6")
    elif sig.stars >= 500: score = 4.0; rationale.append(f"popularity: {sig.stars} stars → 4")
    elif sig.stars >= 100: score = 2.0; rationale.append(f"popularity: {sig.stars} stars → 2")
    else: score = 1.0; rationale.append(f"popularity: only {sig.stars} stars → 1")

    spd = _stars_per_day(sig)
    if spd is not None:
        if spd >= 20:
            score = min(10.0, score + 1.5)
            rationale.append(f"popularity bonus: {spd:.1f} stars/day → +1.5")
        elif spd >= 5:
            score = min(10.0, score + 1.0)
            rationale.append(f"popularity bonus: {spd:.1f} stars/day → +1.0")

    return min(10.0, score)


def _score_governance(sig: RepoSignals, rationale: list[str]) -> float:
    """0-10. Contributor count + open-issue health."""
    score = 0.0
    if sig.contributor_count >= 50:
        score += 5.0
        rationale.append(f"governance: {sig.contributor_count} contributors → +5.0")
    elif sig.contributor_count >= 20:
        score += 4.0
        rationale.append(f"governance: {sig.contributor_count} contributors → +4.0")
    elif sig.contributor_count >= 10:
        score += 3.0
        rationale.append(f"governance: {sig.contributor_count} contributors → +3.0")
    elif sig.contributor_count >= 5:
        score += 2.0
        rationale.append(f"governance: {sig.contributor_count} contributors → +2.0")
    elif sig.contributor_count >= 2:
        score += 1.0
        rationale.append(f"governance: {sig.contributor_count} contributors → +1.0")
    else:
        rationale.append(f"governance: only {sig.contributor_count} contributor(s) → +0")

    # Issue health: more open issues than 1000 = poor; 0 open might mean ignored
    if 1 <= sig.open_issues <= 200:
        score += 3.0
        rationale.append(f"governance: {sig.open_issues} open issues (healthy) → +3.0")
    elif 200 < sig.open_issues <= 500:
        score += 2.0
        rationale.append(f"governance: {sig.open_issues} open issues (manageable) → +2.0")
    elif 500 < sig.open_issues <= 1500:
        score += 1.0
        rationale.append(f"governance: {sig.open_issues} open issues (heavy) → +1.0")
    elif sig.open_issues > 1500:
        rationale.append(f"governance: {sig.open_issues} open issues (backlog risk) → +0")

    # Age signal: older + still active = stronger governance
    age_days = _days_since(sig.created_at)
    if age_days and age_days > 365:
        score += 2.0
        rationale.append(f"governance: {age_days/365:.1f} year(s) old → +2.0 stability")

    return min(10.0, score)


PERMISSIVE_LICENSES = {"mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause", "isc", "0bsd"}
WEAK_COPYLEFT = {"lgpl-2.1", "lgpl-3.0", "mpl-2.0", "epl-2.0"}
STRONG_COPYLEFT = {"gpl-2.0", "gpl-3.0", "agpl-3.0"}


def _score_license_fit(sig: RepoSignals, user_constraint: str, rationale: list[str]) -> float:
    """0-10. License fit against user's constraint.

    user_constraint values:
      - "any" — any license fine
      - "permissive" — MIT/Apache/BSD only
      - "no-agpl" — anything except AGPL
      - "no-copyleft" — permissive only
    """
    license_key = (sig.license_key or "").lower()
    if not license_key:
        rationale.append("license_fit: no license declared → 3.0 (risk)")
        return 3.0

    if user_constraint == "any":
        rationale.append(f"license_fit: {license_key} (no constraint) → 10.0")
        return 10.0
    if user_constraint == "permissive" or user_constraint == "no-copyleft":
        if license_key in PERMISSIVE_LICENSES:
            rationale.append(f"license_fit: {license_key} (permissive ok) → 10.0")
            return 10.0
        if license_key in WEAK_COPYLEFT:
            rationale.append(f"license_fit: {license_key} (weak copyleft) → 4.0")
            return 4.0
        rationale.append(f"license_fit: {license_key} (incompatible) → 1.0")
        return 1.0
    if user_constraint == "no-agpl":
        if license_key == "agpl-3.0":
            rationale.append(f"license_fit: AGPL excluded → 0.0")
            return 0.0
        if license_key in PERMISSIVE_LICENSES or license_key in WEAK_COPYLEFT:
            rationale.append(f"license_fit: {license_key} (non-AGPL ok) → 10.0")
            return 10.0
        if license_key in STRONG_COPYLEFT:
            rationale.append(f"license_fit: {license_key} (GPL — review) → 5.0")
            return 5.0

    rationale.append(f"license_fit: {license_key} (unknown rule) → 5.0")
    return 5.0


# Composite weights (sum to 1.0). Tunable per weight profile.
WEIGHT_PROFILES = {
    "reliable": {"maintenance": 0.35, "popularity": 0.20, "governance": 0.30, "license_fit": 0.15},
    "cutting-edge": {"maintenance": 0.25, "popularity": 0.45, "governance": 0.15, "license_fit": 0.15},
    "commercial": {"maintenance": 0.30, "popularity": 0.15, "governance": 0.20, "license_fit": 0.35},
    "default": {"maintenance": 0.30, "popularity": 0.30, "governance": 0.25, "license_fit": 0.15},
}


def score_repo(sig: RepoSignals, license_constraint: str = "any",
               weight_profile: str = "default") -> RepoScore:
    rationale: list[str] = []
    if sig.fetch_error:
        return RepoScore(full_name=sig.full_name, signals=sig, composite=0.0,
                         rationale=[f"FETCH FAILED: {sig.fetch_error}"])
    m = _score_maintenance(sig, rationale)
    p = _score_popularity(sig, rationale)
    g = _score_governance(sig, rationale)
    l = _score_license_fit(sig, license_constraint, rationale)
    weights = WEIGHT_PROFILES.get(weight_profile, WEIGHT_PROFILES["default"])
    composite = round(
        m * weights["maintenance"]
        + p * weights["popularity"]
        + g * weights["governance"]
        + l * weights["license_fit"],
        2,
    )
    return RepoScore(
        full_name=sig.full_name, signals=sig,
        maintenance=round(m, 2), popularity=round(p, 2),
        governance=round(g, 2), license_fit=round(l, 2),
        composite=composite, rationale=rationale,
    )


def score_candidates(full_names: list[str], license_constraint: str = "any",
                     weight_profile: str = "default",
                     verbose: bool = False) -> list[RepoScore]:
    """Score a list of candidates and return them sorted desc by composite."""
    scored: list[RepoScore] = []
    for fn in full_names:
        if verbose:
            print(f"  fetching {fn}...")
        sig = fetch_repo_signals(fn)
        sc = score_repo(sig, license_constraint=license_constraint, weight_profile=weight_profile)
        scored.append(sc)
    scored.sort(key=lambda s: -s.composite)
    return scored


def score_as_dict(sc: RepoScore) -> dict:
    out = asdict(sc)
    out["signals"] = asdict(sc.signals)
    return out
