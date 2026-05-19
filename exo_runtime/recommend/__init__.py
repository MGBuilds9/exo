"""Data-driven repo recommendation engine.

The LLM never decides which repo is best. It only describes what the
user needs. A scored data layer picks the actual repo.
"""
from .scorer import (
    fetch_repo_signals,
    score_repo,
    score_candidates,
    score_as_dict,
    RepoSignals,
    RepoScore,
)
from .taxonomy import load_taxonomy, list_capabilities, get_capability

__all__ = [
    "fetch_repo_signals", "score_repo", "score_candidates", "score_as_dict",
    "RepoSignals", "RepoScore",
    "load_taxonomy", "list_capabilities", "get_capability",
]
