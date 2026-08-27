"""Bellman-Ford baseline used to validate RIP's final hop-count routes."""

from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Hashable, Iterable


@dataclass(frozen=True)
class PathResult:
    metric: int | float
    predecessor: Hashable | None


def shortest_paths(
    nodes: Iterable[Hashable], edges: Iterable[tuple[Hashable, Hashable, int]], source: Hashable
) -> dict[Hashable, PathResult]:
    """Return hop/cost distances and predecessors using Bellman-Ford.

    The function intentionally accepts an edge list so it can serve as an
    independent correctness baseline for the simulator.
    """
    node_list = list(nodes)
    if source not in node_list:
        raise ValueError(f"source {source!r} is not a node")
    distances = {node: inf for node in node_list}
    predecessors: dict[Hashable, Hashable | None] = {node: None for node in node_list}
    distances[source] = 0
    edge_list = list(edges)

    for _ in range(len(node_list) - 1):
        changed = False
        for start, end, cost in edge_list:
            if cost < 0:
                raise ValueError("RIP-X baseline does not support negative link costs")
            if distances[start] != inf and distances[start] + cost < distances[end]:
                distances[end] = distances[start] + cost
                predecessors[end] = start
                changed = True
        if not changed:
            break

    for start, end, cost in edge_list:
        if distances[start] != inf and distances[start] + cost < distances[end]:
            raise ValueError("negative-cost cycle detected")

    return {node: PathResult(distances[node], predecessors[node]) for node in node_list}
