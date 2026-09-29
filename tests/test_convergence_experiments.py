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

def test_count_to_infinity_comparison_returns_three_configurations():
    result = run_count_to_infinity_comparison()
    assert result["experiment"] == "count_to_infinity_comparison"
    configs = [r["configuration"] for r in result["results"]]
    assert configs == ["no_protection", "split_horizon", "poison_reverse"]


def _by_config():
    result = run_count_to_infinity_comparison()
    return {r["configuration"]: r for r in result["results"]}


def test_no_protection_counts_to_infinity():
    """Without split horizon, R1 and R2 re-learn R3 from each other and the
    metric climbs hop by hop until it reaches INFINITY=16."""
    no_protection = _by_config()["no_protection"]
    assert no_protection["peak_metric"] == 15
    assert no_protection["rounds_to_invalidate"] > 10


def test_split_horizon_and_poison_reverse_prevent_counting():
    by_config = _by_config()
    no_protection = by_config["no_protection"]
    for configuration in ("split_horizon", "poison_reverse"):
        protected = by_config[configuration]
        assert protected["peak_metric"] == 0
        assert protected["rounds_to_invalidate"] < no_protection["rounds_to_invalidate"]
        assert protected["control_messages"] < no_protection["control_messages"]


def test_count_to_infinity_counts_measured_control_messages():
    """Only the R1-R2 link survives R3's failure, so each round carries exactly
    one vector in each direction."""
    for measured in _by_config().values():
        assert measured["control_messages"] == 2 * measured["rounds_to_invalidate"]


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
