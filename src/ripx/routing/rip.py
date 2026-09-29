"""A small, testable RIP v2-style distance-vector control-plane model.

It models the RFC 2453 mechanisms relevant to a simulator: hop-count
metrics, infinity at 16, periodic and triggered updates, route timeout,
garbage collection, split horizon, poison reverse, and route poisoning.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

INFINITY = 16


@dataclass(frozen=True)
class Route:
    destination: str
    metric: int
    next_hop: str | None
    learned_from: str | None
    changed_at: int
    invalid_since: int | None = None

    @property
    def reachable(self) -> bool:
        return self.metric < INFINITY


class RipRouter:
    """Routing-table state for one router in a discrete-time simulation."""

    def __init__(
        self,
        name: str,
        *,
        route_timeout: int = 180,
        garbage_collection: int = 120,
        poison_reverse: bool = True,
        split_horizon: bool = True,
    ) -> None:
        self.name = name
        self.route_timeout = route_timeout
        self.garbage_collection = garbage_collection
        self.poison_reverse = poison_reverse
        self.split_horizon = split_horizon
        self.routes: dict[str, Route] = {name: Route(name, 0, None, None, 0)}
        self.last_heard: dict[tuple[str, str], int] = {}
        self.triggered = True
        self.route_change_count = 0
        # Set when a reachable route becomes unreachable; RIP-X can answer this
        # by requesting full tables from neighbors (RFC 2453 Request message).
        self.lost_route = False

    def restart(self, now: int) -> None:
        """Clear learned state, as a rebooted RIP process starts with only itself."""
        learned = [destination for destination in self.routes if destination != self.name]
        self.routes = {self.name: Route(self.name, 0, None, None, now)}
        self.last_heard.clear()
        self.route_change_count += len(learned)
        self.triggered = True
        self.lost_route = False

    def route(self, destination: str) -> Route | None:
        return self.routes.get(destination)

    def update_for(self, neighbor: str) -> dict[str, int]:
        """Build an advertisement, applying split horizon with poison reverse.

        With ``split_horizon=False`` every route is advertised unchanged to
        every neighbor, which is the unprotected distance-vector behavior that
        allows count-to-infinity. ``poison_reverse`` only has an effect while
        split horizon is enabled.
        """
        advertisement: dict[str, int] = {}
        for destination, route in self.routes.items():
            metric = route.metric
            if self.split_horizon and destination != neighbor and route.learned_from == neighbor:
                if not self.poison_reverse:
                    continue
                metric = INFINITY
            advertisement[destination] = min(metric, INFINITY)
        return advertisement

    def receive(self, neighbor: str, advertisement: dict[str, int], now: int, cost: int = 1) -> bool:
        """Process one complete vector received from an adjacent router.

        ``cost`` is the metric added for the link to ``neighbor``: 1 in
        standard RIP, or a RIP-X link cost.
        """
        changed = False
        for destination, advertised_metric in advertisement.items():
            if destination == self.name:
                continue
            candidate = min(INFINITY, advertised_metric + cost)
            current = self.routes.get(destination)
            self.last_heard[(neighbor, destination)] = now
            should_replace = (
                current is None
                or current.learned_from == neighbor
                or candidate < current.metric
            )
            if should_replace:
                invalid_since = now if candidate == INFINITY else None
                replacement = Route(destination, candidate, neighbor, neighbor, now, invalid_since)
                # Receiving a periodic advertisement with an unchanged metric
                # refreshes liveness above but is not a routing-table change.
                if current is None or current.metric != candidate or current.learned_from != neighbor:
                    if current is not None and current.reachable and candidate == INFINITY:
                        self.lost_route = True
                    self.routes[destination] = replacement
                    self.route_change_count += 1
                    changed = True
        self.triggered = self.triggered or changed
        return changed

    def withdraw_neighbor(self, neighbor: str, now: int) -> bool:
        """Poison routes whose selected next hop has failed."""
        changed = False
        for destination, route in list(self.routes.items()):
            if route.learned_from == neighbor and route.metric != INFINITY:
                self.lost_route = True
                self.routes[destination] = replace(route, metric=INFINITY, changed_at=now, invalid_since=now)
                self.route_change_count += 1
                changed = True
        self.triggered = self.triggered or changed
        return changed

    def age_routes(self, now: int) -> bool:
        """Apply timeout and garbage-collection timers to learned routes."""
        changed = False
        for destination, route in list(self.routes.items()):
            if route.learned_from is None:
                continue
            if route.metric < INFINITY:
                heard_at = self.last_heard.get((route.learned_from, destination), route.changed_at)
                if now - heard_at >= self.route_timeout:
                    self.lost_route = True
                    self.routes[destination] = replace(route, metric=INFINITY, changed_at=now, invalid_since=now)
                    self.route_change_count += 1
                    changed = True
            elif route.invalid_since is not None and now - route.invalid_since >= self.garbage_collection:
                del self.routes[destination]
                self.route_change_count += 1
                changed = True
        self.triggered = self.triggered or changed
        return changed
