"""Deterministic topology factories for baseline RIP experiments."""

from __future__ import annotations

from random import Random
from typing import Any

from ripx.simulation.network import RipNetwork


def _network(names: list[str], options: dict[str, Any]) -> RipNetwork:
    """Create routers on a network built with ``RipNetwork(**options)``."""
    network = RipNetwork(**options)
    for name in names:
        network.add_router(name)
    return network


def line(size: int, **options: Any) -> RipNetwork:
    if size < 2:
        raise ValueError("a line topology needs at least two routers")
    names = [f"R{index}" for index in range(1, size + 1)]
    network = _network(names, options)
    for left, right in zip(names, names[1:]):
        network.add_link(left, right)
    return network


def ring(size: int, **options: Any) -> RipNetwork:
    network = line(size, **options)
    network.add_link(f"R{size}", "R1")
    return network


def star(size: int, **options: Any) -> RipNetwork:
    if size < 2:
        raise ValueError("a star topology needs at least two routers")
    names = [f"R{index}" for index in range(1, size + 1)]
    network = _network(names, options)
    for name in names[1:]:
        network.add_link("R1", name)
    return network


def mesh(size: int, **options: Any) -> RipNetwork:
    """Create a complete mesh with deterministic router names."""
    if size < 2:
        raise ValueError("a mesh topology needs at least two routers")
    names = [f"R{index}" for index in range(1, size + 1)]
    network = _network(names, options)
    for position, left in enumerate(names):
        for right in names[position + 1 :]:
            network.add_link(left, right)
    return network


def random_connected(size: int, *, seed: int = 0, edge_probability: float = 0.25, **options: Any) -> RipNetwork:
    """Create a seeded connected random graph for repeatable experiments."""
    if size < 2:
        raise ValueError("a random topology needs at least two routers")
    if not 0 <= edge_probability <= 1:
        raise ValueError("edge_probability must be between 0 and 1")
    names = [f"R{index}" for index in range(1, size + 1)]
    generator = Random(seed)
    network = _network(names, options)
    edges: set[tuple[str, str]] = set()
    for index in range(1, size):
        parent = names[generator.randrange(index)]
        edges.add(tuple(sorted((names[index], parent))))
    for position, left in enumerate(names):
        for right in names[position + 1 :]:
            edge = (left, right)
            if edge not in edges and generator.random() < edge_probability:
                edges.add(edge)
    for left, right in sorted(edges):
        network.add_link(left, right)
    return network


def scale_free(size: int, *, seed: int = 0, initial_clique: int = 3, **options: Any) -> RipNetwork:
    """Barabási–Albert preferential-attachment topology for power-law degree distribution.

    Each new router connects to ``min(initial_clique, existing)`` existing routers
    chosen with probability proportional to their current degree. The result is a
    hub-and-spoke structure that mimics real-world ISP/internet topologies and is
    useful for testing how RIP handles high-degree hub failures.
    """
    if size < 2:
        raise ValueError("a scale-free topology needs at least two routers")
    if initial_clique < 1:
        raise ValueError("initial_clique must be at least 1")
    names = [f"R{index}" for index in range(1, size + 1)]
    generator = Random(seed)
    network = _network(names, options)
    # Start with a small connected clique
    m = min(initial_clique, size)
    for i in range(m - 1):
        network.add_link(names[i], names[i + 1])
    if m > 2:
        network.add_link(names[0], names[m - 1])
    # Degree list for preferential attachment
    degree: dict[str, int] = {n: 0 for n in names}
    for i in range(m - 1):
        degree[names[i]] += 1
        degree[names[i + 1]] += 1
    if m > 2:
        degree[names[0]] += 1
        degree[names[m - 1]] += 1
    # Attach each remaining node with preferential attachment
    for index in range(m, size):
        new_node = names[index]
        targets_count = min(initial_clique, index)
        existing = names[:index]
        selected: list[str] = []
        remaining = list(existing)
        for _ in range(targets_count):
            if not remaining:
                break
            total = sum(degree[n] for n in remaining) or len(remaining)
            r = generator.uniform(0, total)
            cumulative = 0.0
            chosen = remaining[0]
            for node in remaining:
                cumulative += degree[node] if degree[node] > 0 else 1
                if cumulative >= r:
                    chosen = node
                    break
            selected.append(chosen)
            remaining.remove(chosen)
        for target in selected:
            key = frozenset((new_node, target))
            if key not in network.links:
                network.add_link(new_node, target)
                degree[new_node] = degree.get(new_node, 0) + 1
                degree[target] += 1
    return network


def enterprise_like(*, seed: int = 0, **options: Any) -> RipNetwork:
    """Three-tier enterprise topology: 2 core, 3 distribution, 5 access routers.

    Mirrors a typical campus/branch-office network:
    • Core routers are fully meshed.
    • Each distribution router connects to both core routers.
    • Access routers each connect to one distribution router (round-robin).

    Total: 10 routers, deterministic structure regardless of seed.
    """
    core = ["C1", "C2"]
    dist = ["D1", "D2", "D3"]
    access = ["A1", "A2", "A3", "A4", "A5"]
    names = core + dist + access
    network = _network(names, options)
    # Core full mesh
    for i, left in enumerate(core):
        for right in core[i + 1:]:
            network.add_link(left, right)
    # Distribution → both core routers
    for d in dist:
        for c in core:
            network.add_link(d, c)
    # Access → one distribution router (round-robin)
    for i, a in enumerate(access):
        network.add_link(a, dist[i % len(dist)])
    return network


def iot_edge_like(*, edge_hubs: int = 3, devices_per_hub: int = 4, seed: int = 0, **options: Any) -> RipNetwork:
    """Star-of-stars topology for IoT/edge network experiments.

    One gateway router connects to ``edge_hubs`` hub routers, each of which
    connects to ``devices_per_hub`` leaf device-routers. This models a typical
    IoT edge deployment: a central gateway, intermediate aggregation hubs, and
    resource-constrained leaf nodes. Useful for testing RIP behaviour in
    shallow, high-fan-out topologies.
    """
    if edge_hubs < 1 or devices_per_hub < 1:
        raise ValueError("edge_hubs and devices_per_hub must each be at least 1")
    names = ["GW"]
    hubs = [f"H{i + 1}" for i in range(edge_hubs)]
    names += hubs
    leaves: list[str] = []
    for hub_index in range(edge_hubs):
        for dev_index in range(devices_per_hub):
            leaves.append(f"D{hub_index + 1}_{dev_index + 1}")
    names += leaves
    network = _network(names, options)
    for hub in hubs:
        network.add_link("GW", hub)
    for hub_index, hub in enumerate(hubs):
        for dev_index in range(devices_per_hub):
            network.add_link(hub, f"D{hub_index + 1}_{dev_index + 1}")
    return network
