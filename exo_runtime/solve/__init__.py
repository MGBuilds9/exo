"""exo solve — diagnose + clarify + plan engine.

Reads a data source, extracts candidate issues, ranks them, asks
clarifying questions, produces a structured action plan.
"""
from .reader import read_data_source, IssueCandidate, DataDigest
from .ranker import rank_issues
from .planner import build_plan, ActionPlan

__all__ = [
    "read_data_source", "IssueCandidate", "DataDigest",
    "rank_issues",
    "build_plan", "ActionPlan",
]
