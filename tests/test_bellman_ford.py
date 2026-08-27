from math import inf

from ripx.routing.bellman_ford import shortest_paths


def test_finds_lowest_cost_path_and_predecessor():
    paths = shortest_paths(
        ["A", "B", "C", "D"],
        [("A", "B", 1), ("B", "A", 1), ("B", "C", 1), ("C", "B", 1), ("A", "C", 5), ("C", "A", 5)],
        "A",
    )
    assert paths["C"].metric == 2
    assert paths["C"].predecessor == "B"
    assert paths["D"].metric == inf
