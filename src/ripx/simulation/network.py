"""Discrete-round network simulation for reproducible RIP experiments."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace

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
        self.link_baselines: dict[frozenset[str], Link] = {}
        self.failed_routers: set[str] = set()
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
        link = Link(left, right, **telemetry)
        self.links[key] = link
        self.link_baselines[key] = link

    def neighbors(self, router: str) -> list[str]:
        if router in self.failed_routers:
            return []
        result: list[str] = []
        for link in self.links.values():
            if not link.up:
                continue
            if link.left in self.failed_routers or link.right in self.failed_routers:
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

    def set_link_conditions(
        self,
        left: str,
        right: str,
        *,
        latency_ms: float | None = None,
        packet_loss: float | None = None,
        bandwidth_mbps: float | None = None,
    ) -> None:
        """Change measurable link conditions without changing RIP hop cost."""
        key = frozenset((left, right))
        link = self.links[key]
        if latency_ms is not None and latency_ms < 0:
            raise ValueError("latency_ms must not be negative")
        if packet_loss is not None and not 0 <= packet_loss <= 1:
            raise ValueError("packet_loss must be between 0 and 1")
        if bandwidth_mbps is not None and bandwidth_mbps <= 0:
            raise ValueError("bandwidth_mbps must be positive")
        self.links[key] = replace(
            link,
            latency_ms=link.latency_ms if latency_ms is None else latency_ms,
            packet_loss=link.packet_loss if packet_loss is None else packet_loss,
            bandwidth_mbps=link.bandwidth_mbps if bandwidth_mbps is None else bandwidth_mbps,
        )

    def restore_link_conditions(self, left: str, right: str) -> None:
        """Restore a link's baseline telemetry values while preserving its state."""
        key = frozenset((left, right))
        current = self.links[key]
        baseline = self.link_baselines[key]
        self.links[key] = replace(
            current,
            bandwidth_mbps=baseline.bandwidth_mbps,
            latency_ms=baseline.latency_ms,
            packet_loss=baseline.packet_loss,
        )

    def fail_router(self, router: str) -> None:
        """Take a router offline and poison routes that depend on it."""
        if router not in self.routers:
            raise ValueError(f"router {router!r} does not exist")
        if router in self.failed_routers:
            return
        previous_neighbors = self.neighbors(router)
        self.failed_routers.add(router)
        for neighbor in previous_neighbors:
            self.routers[neighbor].withdraw_neighbor(router, self.now)

    def recover_router(self, router: str) -> None:
        """Return a failed router to service and trigger neighbor exchanges."""
        if router not in self.routers:
            raise ValueError(f"router {router!r} does not exist")
        if router not in self.failed_routers:
            return
        self.failed_routers.remove(router)
        self.routers[router].triggered = True
        for neighbor in self.neighbors(router):
            self.routers[neighbor].triggered = True

    def route_path(self, source: str, destination: str) -> list[str] | None:
        """Follow the current RIP next hops to return a forwarding path.

        Returning ``None`` means the destination cannot be safely forwarded to
        using the current table. This also detects an unexpected forwarding
        loop rather than reporting a fabricated path.
        """
        if source not in self.routers or destination not in self.routers:
            raise ValueError("source and destination must be existing routers")
        if source in self.failed_routers or destination in self.failed_routers:
            return None
        path = [source]
        current = source
        while current != destination:
            route = self.routers[current].route(destination)
            if route is None or not route.reachable or route.next_hop is None:
                return None
            next_hop = route.next_hop
            if next_hop not in self.neighbors(current) or next_hop in path:
                return None
            path.append(next_hop)
            current = next_hop
            if len(path) > len(self.routers):
                return None
        return path

    def step(self) -> ConvergenceResult:
        """Deliver a snapshot of every active router's vector to each neighbor."""
        outgoing = [
            (source, neighbor, self.routers[source].update_for(neighbor))
            for source in sorted(self.routers)
            for neighbor in self.neighbors(source)
        ]
        for name, router in self.routers.items():
            if name not in self.failed_routers:
                router.triggered = False
        self.now += 1
        changed = False
        for source, target, vector in outgoing:
            changed = self.routers[target].receive(source, vector, self.now) or changed
        for name, router in self.routers.items():
            if name not in self.failed_routers:
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
