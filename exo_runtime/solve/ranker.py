"""Rank issues by impact × actionability.

Impact = severity from extraction.
Actionability = is this fixable by us, or upstream / external?
"""
from __future__ import annotations

from .reader import IssueCandidate


# Heuristics: words in name/description that suggest actionability
SELF_FIXABLE_KEYWORDS = (
    "config", "permission", "mount", "restart", "stale", "expired", "deprecated",
    "backup", "stuck", "queue", "log", "disk", "swap", "memory", "rotate",
    "credential", "expired", "outdated", "service", "process",
)

EXTERNAL_KEYWORDS = (
    "vendor", "upstream", "provider", "outage", "isp", "internet", "physical",
    "hardware fail", "ssd dead", "drive dead", "power",
)


def _estimate_actionability(issue: IssueCandidate) -> int:
    """0-10 scale. 10 = trivially actionable, 0 = totally external."""
    text = (issue.name + " " + issue.description).lower()
    score = 5  # neutral default
    for kw in SELF_FIXABLE_KEYWORDS:
        if kw in text:
            score += 2
            break
    for kw in EXTERNAL_KEYWORDS:
        if kw in text:
            score -= 3
            break
    if issue.evidence:
        score += 1  # evidence links → more actionable
    if issue.suggested_fix_hints:
        score += 1
    return max(0, min(10, score))


def rank_issues(issues: list[IssueCandidate], top_n: int = 10) -> list[tuple[IssueCandidate, int]]:
    """Rank by impact × actionability. Returns top_n with composite score."""
    ranked = []
    for issue in issues:
        action = _estimate_actionability(issue)
        composite = issue.severity * action  # 0-100
        ranked.append((issue, composite, action))
    ranked.sort(key=lambda x: -x[1])
    return [(i, c) for i, c, _a in ranked[:top_n]]
