import pytest
from math import inf

from ripx.analytics.experiment import run_bellman_ford_validation
from ripx.routing.bellman_ford import shortest_paths
from ripx.simulation.topologies import line, mesh, ring


def test_finds_lowest_cost_path_and_predecessor():
    paths = shortest_paths(
        ["A", "B", "C", "D"],
        [("A", "B", 1), ("B", "A", 1), ("B", "C", 1), ("C", "B", 1), ("A", "C", 5), ("C", "A", 5)],
        "A",
    )
    assert paths["C"].metric == 2
    assert paths["C"].predecessor == "B"
    assert paths["D"].metric == inf


def test_negative_edge_raises_value_error():
    with pytest.raises(ValueError, match="negative link costs"):
        shortest_paths(["A", "B"], [("A", "B", -1)], "A")


def test_bellman_ford_matches_rip_line():
    """Converged RIP hop counts must exactly equal Bellman-Ford shortest paths on a line."""
    result = run_bellman_ford_validation("line", 6)
    assert result["valid"], f"Mismatches found: {result['mismatches']}"


def test_bellman_ford_matches_rip_ring():
    """Converged RIP hop counts must match Bellman-Ford on a ring topology."""
    result = run_bellman_ford_validation("ring", 6)
    assert result["valid"], f"Mismatches found: {result['mismatches']}"


def test_bellman_ford_matches_rip_mesh():
    """In a full mesh every route is distance 1 — a trivial correctness check."""
    result = run_bellman_ford_validation("mesh", 5)
    assert result["valid"], f"Mismatches found: {result['mismatches']}"
