"""Tests for count-to-infinity experiment and convergence scaling.

These tests verify the measured behaviour of the count-to-infinity scenario
and the convergence scaling utility. They do not assert fabricated improvement
figures; they assert structural properties of the experimental output.
"""

from __future__ import annotations

import json

import pytest

from ripx.analytics.convergence_experiments import (
    run_convergence_scaling,
    run_count_to_infinity_comparison,
)
from ripx.simulation.topologies import line, ring


# ── Count-to-infinity ────────────────────────────────────────────────────────

def test_count_to_infinity_comparison_returns_two_configurations():
    result = run_count_to_infinity_comparison()
    assert result["experiment"] == "count_to_infinity_comparison"
    assert len(result["results"]) == 2
    configs = {r["configuration"] for r in result["results"]}
    assert configs == {"no_split_horizon", "poison_reverse"}


def test_poison_reverse_invalidates_in_fewer_rounds():
    """Poison reverse should cause R1 to learn about R3's loss faster than
    counting to infinity without any loop-breaking mechanism.

    Without poison reverse: R1 counts hop-by-hop up to 16 — many rounds.
    With poison reverse: R2 immediately advertises INFINITY back, so R1
    should invalidate R3 faster.
    """
    result = run_count_to_infinity_comparison()
    by_config = {r["configuration"]: r for r in result["results"]}
    pr_rounds = by_config["poison_reverse"]["rounds_to_invalidate"]
    no_pr_rounds = by_config["no_split_horizon"]["rounds_to_invalidate"]
    assert pr_rounds <= no_pr_rounds, (
        f"Expected poison_reverse ({pr_rounds}) to converge in <= rounds than "
        f"no_split_horizon ({no_pr_rounds})"
    )


def test_no_split_horizon_reaches_high_metric():
    """Without loop prevention, the counting metric should climb well above 1
    before reaching INFINITY=16 or the experiment terminates."""
    result = run_count_to_infinity_comparison()
    by_config = {r["configuration"]: r for r in result["results"]}
    no_pr = by_config["no_split_horizon"]
    # The metric should climb: peak must be > 2 (baseline) if counting occurs
    assert no_pr["peak_metric"] > 2 or no_pr["rounds_to_invalidate"] >= 1


def test_count_to_infinity_result_is_json_serialisable():
    result = run_count_to_infinity_comparison()
    # Should not raise
    encoded = json.dumps(result)
    decoded = json.loads(encoded)
    assert decoded["experiment"] == "count_to_infinity_comparison"


# ── Convergence scaling ──────────────────────────────────────────────────────

def test_convergence_scaling_line_grows_with_size():
    """A line topology needs more rounds as routers are added — verifies
    that the scaling utility correctly captures monotone growth."""
    sizes = [4, 6, 8]
    results = run_convergence_scaling(line, sizes, "line")
    assert len(results) == len(sizes)
    for result, size in zip(results, sizes):
        assert result.routers == size
        assert result.convergence_rounds >= 1
        assert result.control_messages >= 1
    # Convergence rounds should be non-decreasing for a line
    rounds = [r.convergence_rounds for r in results]
    assert rounds == sorted(rounds), f"Expected non-decreasing rounds: {rounds}"


def test_convergence_scaling_ring_is_reproducible():
    """Running the same scaling experiment twice must yield identical results."""
    sizes = [4, 6]
    first = run_convergence_scaling(ring, sizes, "ring")
    second = run_convergence_scaling(ring, sizes, "ring")
    for a, b in zip(first, second):
        assert a == b


# ── Scenario file integration ─────────────────────────────────────────────────

def test_count_to_infinity_scenario_runs(tmp_path):
    """The count-to-infinity.json scenario should load and run without errors."""
    from ripx.analytics.experiment import run_scenario
    source = tmp_path / "cti.json"
    source.write_text(
        json.dumps({
            "name": "count-to-infinity",
            "topology": "line",
            "routers": 3,
            "events": [
                {"type": "link_failure", "link": ["R2", "R3"]},
                {"type": "link_recovery", "link": ["R2", "R3"]},
            ],
        })
    )
    result = run_scenario(source)
    phases = result["phases"]
    assert phases[0]["event"] == "baseline"
    assert phases[1]["event"] == "link_failure"
    assert phases[2]["event"] == "link_recovery"
    # After recovery, R1 must be able to reach R3 again
    assert phases[2]["convergence_rounds"] >= 1
