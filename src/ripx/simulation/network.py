"""Discrete-round network simulation for reproducible RIP experiments."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace

from ripx.routing.metrics import HopCountCost, LinkCostPolicy
from ripx.routing.rip import RipRouter
from ripx.routing.scheduling import FixedUpdateSchedule, UpdateSchedule


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

    def __init__(
        self,
        *,
        route_timeout: int = 180,
        garbage_collection: int = 120,
        poison_reverse: bool = True,
        split_horizon: bool = True,
        update_interval: int = 1,
        triggered_updates: bool = True,
        schedule: UpdateSchedule | None = None,
        cost_policy: LinkCostPolicy | None = None,
        request_on_loss: bool = False,
    ) -> None:
        self.schedule = schedule if schedule is not None else FixedUpdateSchedule(update_interval)
        if self.schedule.max_interval >= route_timeout:
            raise ValueError("update_interval must be shorter than route_timeout")
        self.route_timeout = route_timeout
        self.garbage_collection = garbage_collection
        self.poison_reverse = poison_reverse
        self.split_horizon = split_horizon
        self.triggered_updates = triggered_updates
        self.request_on_loss = request_on_loss
        self.cost_policy = cost_policy if cost_policy is not None else HopCountCost()
        self.link_costs: dict[frozenset[str], int] = {}
        self.link_utilization: dict[frozenset[str], float] = {}
        self._change_counts: dict[str, int] = {}
        self._periodic_change_counts: dict[str, int] = {}
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
            split_horizon=self.split_horizon,
        )
        self.schedule.register(name)
        self._change_counts[name] = 0

    def add_link(self, left: str, right: str, **telemetry: float) -> None:
        if left == right or left not in self.routers or right not in self.routers:
            raise ValueError("links must connect two existing, distinct routers")
        key = frozenset((left, right))
        link = Link(left, right, **telemetry)
        self.links[key] = link
        self.link_baselines[key] = link
        self.link_costs[key] = self._compute_cost(key)

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
        self.refresh_link_costs()

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
        self.refresh_link_costs()

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
        self.routers[router].restart(self.now)
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

    @property
    def update_interval(self) -> int:
        """The fixed interval, or the longest interval an adaptive schedule may use."""
        return self.schedule.max_interval

    def link_cost(self, left: str, right: str) -> int:
        return self.link_costs[frozenset((left, right))]

    def _compute_cost(self, key: frozenset[str], previous: int | None = None) -> int:
        link = self.links[key]
        return self.cost_policy.cost(
            utilization=self.link_utilization.get(key, 0.0),
            latency_ms=link.latency_ms,
            packet_loss=link.packet_loss,
            previous=previous,
        )

    def set_link_costs(self, costs: dict[frozenset[str], int]) -> list[frozenset[str]]:
        """Install explicit link costs and trigger updates at changed links."""
        changed: list[frozenset[str]] = []
        for key, cost in costs.items():
            if key not in self.links:
                raise ValueError(f"unknown link {sorted(key)}")
            if cost < 1:
                raise ValueError("link cost must be at least 1")
            if self.link_costs.get(key) != cost:
                self.link_costs[key] = cost
                changed.append(key)
                for router in key:
                    self.routers[router].triggered = True
        return changed

    def refresh_link_costs(self) -> list[frozenset[str]]:
        """Recompute every link cost from current conditions and measured load."""
        costs = {key: self._compute_cost(key, self.link_costs.get(key)) for key in self.links}
        return self.set_link_costs(costs)

    def record_utilization(self, utilization: dict[frozenset[str], float]) -> list[frozenset[str]]:
        """Store measured link utilization and refresh costs that depend on it."""
        self.link_utilization = dict(utilization)
        return self.refresh_link_costs()

    def is_periodic_round(self, router: str | None = None) -> bool:
        """Whether the round about to run is a scheduled periodic update.

        With a fixed schedule this is the same for every router. With an
        adaptive schedule pass ``router``; without it, this reports whether any
        router is due.
        """
        return self.schedule.is_due(router, self.now)

    def should_advertise(self, router: str) -> bool:
        """Decide whether ``router`` sends its vector in the upcoming round.

        Every router sends on periodic rounds. Between them, a router sends
        only when a routing change or topology event marked it as triggered.
        With the default ``update_interval=1`` every round is periodic.
        """
        if self.schedule.is_due(router, self.now):
            return True
        return self.triggered_updates and self.routers[router].triggered

    def has_pending_updates(self) -> bool:
        """Whether any active router holds changes it has not advertised yet."""
        return any(
            router.triggered or (self.request_on_loss and router.lost_route)
            for name, router in self.routers.items()
            if name not in self.failed_routers
        )

    def _record_route_changes(self) -> None:
        """Tell the schedule which routers' tables changed since the last check."""
        for name, router in self.routers.items():
            if router.route_change_count != self._change_counts[name]:
                self._change_counts[name] = router.route_change_count
                self.schedule.record_change(name, self.now)

    def step(self) -> ConvergenceResult:
        """Deliver a snapshot of each advertising router's vector to its neighbors."""
        # Changes made by failure events between rounds.
        self._record_route_changes()
        due = {
            name
            for name in self.routers
            if name not in self.failed_routers and self.schedule.is_due(name, self.now)
        }
        senders = [
            name
            for name in sorted(self.routers)
            if name not in self.failed_routers
            and (name in due or (self.triggered_updates and self.routers[name].triggered))
        ]
        outgoing = [
            (source, neighbor, self.routers[source].update_for(neighbor))
            for source in senders
            for neighbor in self.neighbors(source)
        ]
        # RIP-X: a router that lost a route asks its neighbors for their full
        # tables, so an alternative path is heard without waiting for their
        # next periodic update. Neighbors answer in the following round.
        requests = 0
        for name, router in self.routers.items():
            if router.lost_route:
                router.lost_route = False
                if self.request_on_loss and name not in self.failed_routers:
                    for neighbor in self.neighbors(name):
                        self.routers[neighbor].triggered = True
                        requests += 1
        # Only routers that advertised have delivered their pending changes.
        for name in senders:
            router = self.routers[name]
            router.triggered = False
            if name in due:
                stable = self._periodic_change_counts.get(name) == router.route_change_count
                self._periodic_change_counts[name] = router.route_change_count
                self.schedule.record_periodic(name, self.now, stable)
        self.now += 1
        changed = False
        for source, target, vector in outgoing:
            cost = self.link_costs[frozenset((source, target))]
            changed = self.routers[target].receive(source, vector, self.now, cost) or changed
        for name, router in self.routers.items():
            if name not in self.failed_routers:
                changed = router.age_routes(self.now) or changed
        self._record_route_changes()
        return ConvergenceResult(1, len(outgoing) + requests, changed)

    def converge(self, max_rounds: int = 100) -> ConvergenceResult:
        messages = 0
        for round_number in range(1, max_rounds + 1):
            result = self.step()
            messages += result.control_messages
            if not result.changed and not self.has_pending_updates():
                return ConvergenceResult(round_number, messages, False)
        return ConvergenceResult(max_rounds, messages, True)
