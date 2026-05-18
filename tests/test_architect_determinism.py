"""Verify the architect's recommendation logic is deterministic.

The README claims `exo architect` is rule-based (not LLM-in-the-loop), so
the same answers should produce identical recommendations every time.

This test runs each recommendation function twice with the same inputs
and asserts byte-equal output.

Run: python -m pytest tests/test_architect_determinism.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cli.architect_cmd import (
    recommend_memory_tier,
    recommend_default_model,
    stub_actors,
    slugify,
)


def test_slugify_deterministic():
    assert slugify("Hello World") == slugify("Hello World") == "hello-world"
    assert slugify("My-Sim_123") == slugify("My-Sim_123") == "my-sim-123"
    assert slugify("   leading/trailing???   ") == slugify("   leading/trailing???   ") == "leading-trailing"


def test_recommend_memory_tier_deterministic():
    for need in ("conversation", "relational", "knowledge", "everything"):
        a = recommend_memory_tier(need)
        b = recommend_memory_tier(need)
        assert a == b, f"recommend_memory_tier({need!r}) not deterministic: {a} != {b}"


def test_recommend_default_model_deterministic():
    for pref in ("claude-oauth", "ollama-cloud", "local-ollama", "mixed"):
        a = recommend_default_model(pref)
        b = recommend_default_model(pref)
        assert a == b, f"recommend_default_model({pref!r}) not deterministic"


def test_stub_actors_deterministic():
    # Same inputs must produce identical actor list (order + content)
    cases = [
        ("small", "claude-oauth", "organizational"),
        ("medium", "ollama-cloud/x", "social-platform"),
        ("small", "local-ollama/y", "customer-service"),
        ("small", "claude-oauth", "incident-response"),
    ]
    for scale, model, kind in cases:
        a = stub_actors(scale, model, kind)
        b = stub_actors(scale, model, kind)
        assert a == b, f"stub_actors({scale!r},{model!r},{kind!r}) not deterministic"
        # Sanity: all actors carry the same model
        for actor in a:
            assert actor["model"] == model


def test_recommended_memory_tier_correct():
    # Spot-check the rules
    assert recommend_memory_tier("conversation")["tier"] == "none"
    assert recommend_memory_tier("relational")["tier"] == "graph"
    assert recommend_memory_tier("knowledge")["tier"] == "vector"
    e = recommend_memory_tier("everything")
    assert "vector" in e["tier"] and "graph" in e["tier"] and "sql" in e["tier"]


def test_recommended_default_model_routes_correctly():
    assert recommend_default_model("claude-oauth") == "claude-oauth"
    assert "ollama-cloud" in recommend_default_model("ollama-cloud")
    assert "local-ollama" in recommend_default_model("local-ollama")


def test_stub_actors_scale_respected():
    small = stub_actors("small", "test-model", "organizational")
    assert 3 <= len(small) <= 8, f"small scale should produce 3-8 actors, got {len(small)}"
    medium = stub_actors("medium", "test-model", "social-platform")
    assert len(medium) >= 8, f"medium scale should produce >=8 actors, got {len(medium)}"


if __name__ == "__main__":
    # Allow running without pytest
    import traceback
    tests = [
        test_slugify_deterministic,
        test_recommend_memory_tier_deterministic,
        test_recommend_default_model_deterministic,
        test_stub_actors_deterministic,
        test_recommended_memory_tier_correct,
        test_recommended_default_model_routes_correctly,
        test_stub_actors_scale_respected,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as e:
            failures += 1
            print(f"  FAIL  {t.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(0 if failures == 0 else 1)
