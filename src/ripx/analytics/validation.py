"""Routing-state checks against the independent Bellman-Ford reference."""

from __future__ import annotations

from math import inf

from ripx.routing.bellman_ford import shortest_paths
from ripx.routing.rip import INFINITY
from ripx.simulation.network import RipNetwork


def active_edges(network: RipNetwork) -> list[tuple[str, str, int]]:
    """Directed edges of usable links, weighted by their current RIP-X cost."""
    edges: list[tuple[str, str, int]] = []
    for key, link in network.links.items():
        if not link.up or link.left in network.failed_routers or link.right in network.failed_routers:
            continue
        cost = network.link_costs[key]
        edges.append((link.left, link.right, cost))
        edges.append((link.right, link.left, cost))
    return edges


def expected_metrics(network: RipNetwork) -> dict[str, dict[str, int | None]]:
    """Bellman-Ford metric for every active source/destination pair.

    ``None`` means RIP should hold no reachable route: the destination is
    failed, disconnected, or at least INFINITY away.
    """
    active = [name for name in network.routers if name not in network.failed_routers]
    edges = active_edges(network)
    expected: dict[str, dict[str, int | None]] = {}
    for source in active:
        paths = shortest_paths(active, edges, source)
        row: dict[str, int | None] = {}
        for destination in network.routers:
            if destination == source:
                continue
            distance = paths[destination].metric if destination in paths else inf
            row[destination] = None if distance == inf or distance >= INFINITY else int(distance)
        expected[source] = row
    return expected


def trace_next_hops(network: RipNetwork, source: str, destination: str) -> str:
    """Follow next hops from ``source`` and classify the outcome.

    Returns ``"delivered"``, ``"blackhole"`` (no usable route on the way) or
    ``"loop"`` (a router is visited twice).
    """
    current = source
    visited = {source}
    while current != destination:
        route = network.routers[current].route(destination)
        if route is None or not route.reachable or route.next_hop is None:
            return "blackhole"
        if route.next_hop not in network.neighbors(current):
            return "blackhole"
        current = route.next_hop
        if current in visited:
            return "loop"
        visited.add(current)
    return "delivered"


def routing_state(network: RipNetwork, expected: dict[str, dict[str, int | None]]) -> dict[str, int]:
    """Count incorrect, black-holed and looping pairs in the current tables.

    ``blackhole`` counts reachable destinations whose traffic would be
    dropped. ``loop`` counts pairs whose forwarding path revisits a router,
    including loops towards destinations that are no longer reachable.
    ``stale`` counts routes still held as reachable to unreachable destinations.
    """
    counts = {"pairs": 0, "incorrect": 0, "blackhole": 0, "loop": 0, "stale": 0}
    for source, row in expected.items():
        router = network.routers[source]
        for destination, metric in row.items():
            counts["pairs"] += 1
            route = router.route(destination)
            held = route.metric if route is not None and route.reachable else None
            if held != metric:
                counts["incorrect"] += 1
            if metric is not None:
                outcome = trace_next_hops(network, source, destination)
                if outcome != "delivered":
                    counts[outcome] += 1
            elif held is not None:
                counts["stale"] += 1
                if trace_next_hops(network, source, destination) == "loop":
                    counts["loop"] += 1
    return counts
