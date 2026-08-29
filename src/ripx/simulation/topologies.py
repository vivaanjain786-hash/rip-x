"""Deterministic topology factories for baseline RIP experiments."""

from __future__ import annotations

from random import Random

from ripx.simulation.network import RipNetwork


def _network(names: list[str]) -> RipNetwork:
    network = RipNetwork()
    for name in names:
        network.add_router(name)
    return network


def line(size: int) -> RipNetwork:
    if size < 2:
        raise ValueError("a line topology needs at least two routers")
    names = [f"R{index}" for index in range(1, size + 1)]
    network = _network(names)
    for left, right in zip(names, names[1:]):
        network.add_link(left, right)
    return network


def ring(size: int) -> RipNetwork:
    network = line(size)
    network.add_link(f"R{size}", "R1")
    return network


def star(size: int) -> RipNetwork:
    if size < 2:
        raise ValueError("a star topology needs at least two routers")
    names = [f"R{index}" for index in range(1, size + 1)]
    network = _network(names)
    for name in names[1:]:
        network.add_link("R1", name)
    return network


def mesh(size: int) -> RipNetwork:
    """Create a complete mesh with deterministic router names."""
    if size < 2:
        raise ValueError("a mesh topology needs at least two routers")
    names = [f"R{index}" for index in range(1, size + 1)]
    network = _network(names)
    for position, left in enumerate(names):
        for right in names[position + 1 :]:
            network.add_link(left, right)
    return network


def random_connected(size: int, *, seed: int = 0, edge_probability: float = 0.25) -> RipNetwork:
    """Create a seeded connected random graph for repeatable experiments."""
    if size < 2:
        raise ValueError("a random topology needs at least two routers")
    if not 0 <= edge_probability <= 1:
        raise ValueError("edge_probability must be between 0 and 1")
    names = [f"R{index}" for index in range(1, size + 1)]
    generator = Random(seed)
    network = _network(names)
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
