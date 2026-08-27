"""Discrete-round network simulation for reproducible RIP experiments."""

from __future__ import annotations

from dataclasses import dataclass

from ripx.routing.rip import RipRouter


@dataclass(frozen=True)
class Link:
    left: str
    right: str
    bandwidth_mbps: float = 100.0
    latency_ms: float = 1.0
    packet_loss: float = 0.0
    up: bool = True


@dataclass(frozen=True)
class ConvergenceResult:
    rounds: int
    control_messages: int
    changed: bool


class RipNetwork:
    """Undirected router/link abstraction with atomic RIP update rounds."""

    def __init__(self, *, route_timeout: int = 180, garbage_collection: int = 120, poison_reverse: bool = True) -> None:
        self.route_timeout = route_timeout
        self.garbage_collection = garbage_collection
        self.poison_reverse = poison_reverse
        self.routers: dict[str, RipRouter] = {}
        self.links: dict[frozenset[str], Link] = {}
        self.now = 0

    def add_router(self, name: str) -> None:
        if name in self.routers:
            raise ValueError(f"router {name!r} already exists")
        self.routers[name] = RipRouter(
            name,
            route_timeout=self.route_timeout,
            garbage_collection=self.garbage_collection,
            poison_reverse=self.poison_reverse,
        )

    def add_link(self, left: str, right: str, **telemetry: float) -> None:
        if left == right or left not in self.routers or right not in self.routers:
            raise ValueError("links must connect two existing, distinct routers")
        key = frozenset((left, right))
        self.links[key] = Link(left, right, **telemetry)

    def neighbors(self, router: str) -> list[str]:
        result: list[str] = []
        for link in self.links.values():
            if not link.up:
                continue
            if link.left == router:
                result.append(link.right)
            elif link.right == router:
                result.append(link.left)
        return sorted(result)

    def fail_link(self, left: str, right: str) -> None:
        key = frozenset((left, right))
        link = self.links[key]
        self.links[key] = Link(link.left, link.right, link.bandwidth_mbps, link.latency_ms, link.packet_loss, False)
        self.routers[left].withdraw_neighbor(right, self.now)
        self.routers[right].withdraw_neighbor(left, self.now)

    def recover_link(self, left: str, right: str) -> None:
        key = frozenset((left, right))
        link = self.links[key]
        self.links[key] = Link(link.left, link.right, link.bandwidth_mbps, link.latency_ms, link.packet_loss, True)
        self.routers[left].triggered = True
        self.routers[right].triggered = True

    def step(self) -> ConvergenceResult:
        """Deliver a snapshot of every active router's vector to each neighbor."""
        outgoing = [
            (source, neighbor, self.routers[source].update_for(neighbor))
            for source in sorted(self.routers)
            for neighbor in self.neighbors(source)
        ]
        for router in self.routers.values():
            router.triggered = False
        self.now += 1
        changed = False
        for source, target, vector in outgoing:
            changed = self.routers[target].receive(source, vector, self.now) or changed
        for router in self.routers.values():
            changed = router.age_routes(self.now) or changed
        return ConvergenceResult(1, len(outgoing), changed)

    def converge(self, max_rounds: int = 100) -> ConvergenceResult:
        messages = 0
        for round_number in range(1, max_rounds + 1):
            result = self.step()
            messages += result.control_messages
            if not result.changed:
                return ConvergenceResult(round_number, messages, False)
        return ConvergenceResult(max_rounds, messages, True)
