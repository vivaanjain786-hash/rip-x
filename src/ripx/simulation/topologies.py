"""Deterministic topology factories for baseline RIP experiments."""

from __future__ import annotations

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
