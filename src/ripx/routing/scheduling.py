"""Periodic update schedules for RIP routers.

``FixedUpdateSchedule`` is standard RIP: every router sends its full vector
every ``interval`` rounds. ``AdaptiveUpdateSchedule`` is the RIP-X mechanism:
each router lengthens its own periodic interval while its routing table stays
unchanged, and falls back to the minimum interval as soon as a route changes.
Triggered updates are independent of either schedule and are handled by the
network.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class FixedUpdateSchedule:
    """Standard RIP: all routers send on rounds that are multiples of ``interval``."""

    name = "fixed"

    def __init__(self, interval: int = 1) -> None:
        if interval < 1:
            raise ValueError("update_interval must be at least 1")
        self.interval = interval

    @property
    def max_interval(self) -> int:
        return self.interval

    def register(self, router: str) -> None:
        pass

    def current_interval(self, router: str) -> int:
        return self.interval

    def is_due(self, router: str | None, now: int) -> bool:
        return now % self.interval == 0

    def record_periodic(self, router: str, now: int, stable: bool) -> None:
        pass

    def record_change(self, router: str, now: int) -> None:
        pass

    def describe(self) -> dict[str, object]:
        return {"type": self.name, "interval": self.interval}


@dataclass
class AdaptiveUpdateSchedule:
    """RIP-X adaptive periodic updates.

    Each router starts at ``min_interval``. After a periodic update sent while
    its table was unchanged since its previous periodic update, the router
    multiplies its interval by ``growth`` up to ``max_interval``. Any change to
    the router's table resets it to ``min_interval`` and pulls its next
    periodic update forward to at most ``min_interval`` rounds away.

    The hypothesis under test: in stable periods this sends fewer control
    messages than a fixed schedule, while triggered updates keep convergence
    after topology changes close to the fixed schedule.
    """

    min_interval: int = 5
    max_interval: int = 20
    growth: int = 2
    intervals: dict[str, int] = field(default_factory=dict)
    next_due: dict[str, int] = field(default_factory=dict)

    name = "adaptive"

    def __post_init__(self) -> None:
        if self.min_interval < 1:
            raise ValueError("min_interval must be at least 1")
        if self.max_interval < self.min_interval:
            raise ValueError("max_interval must be at least min_interval")
        if self.growth < 1:
            raise ValueError("growth must be at least 1")

    def register(self, router: str) -> None:
        self.intervals[router] = self.min_interval
        self.next_due[router] = 0

    def current_interval(self, router: str) -> int:
        return self.intervals[router]

    def is_due(self, router: str | None, now: int) -> bool:
        if router is None:
            return any(now >= due for due in self.next_due.values())
        return now >= self.next_due[router]

    def record_periodic(self, router: str, now: int, stable: bool) -> None:
        if stable:
            self.intervals[router] = min(self.max_interval, self.intervals[router] * self.growth)
        self.next_due[router] = now + self.intervals[router]

    def record_change(self, router: str, now: int) -> None:
        self.intervals[router] = self.min_interval
        self.next_due[router] = min(self.next_due[router], now + self.min_interval)

    def describe(self) -> dict[str, object]:
        return {
            "type": self.name,
            "min_interval": self.min_interval,
            "max_interval": self.max_interval,
            "growth": self.growth,
        }


UpdateSchedule = FixedUpdateSchedule | AdaptiveUpdateSchedule


def schedule_from_config(config: dict[str, object] | None, default_interval: int = 1) -> UpdateSchedule:
    """Build a schedule from a scenario's ``updates`` object."""
    if not config:
        return FixedUpdateSchedule(default_interval)
    kind = config.get("type", "fixed")
    if kind == "fixed":
        return FixedUpdateSchedule(int(config.get("interval", default_interval)))
    if kind == "adaptive":
        return AdaptiveUpdateSchedule(
            min_interval=int(config.get("min_interval", 5)),
            max_interval=int(config.get("max_interval", 20)),
            growth=int(config.get("growth", 2)),
        )
    raise ValueError("updates.type must be 'fixed' or 'adaptive'")
