"""Link-cost policies for RIP-X route selection.

Standard RIP charges every link a cost of 1, so route selection is pure hop
count. RIP-X's congestion-aware policy charges a small integer cost that grows
with measured utilization, latency and packet loss. Costs stay small because
RIP's metric still saturates at INFINITY = 16.
"""

from __future__ import annotations

from dataclasses import dataclass


class HopCountCost:
    """Standard RIP: every usable link costs one hop."""

    name = "hop_count"
    max_cost = 1

    def cost(self, *, utilization: float, latency_ms: float, packet_loss: float, previous: int | None = None) -> int:
        return 1

    def describe(self) -> dict[str, object]:
        return {"type": self.name}


@dataclass(frozen=True)
class CongestionAwareCost:
    """Integer link cost of ``1 + penalties``, capped at ``max_cost``.

    Penalties:
    - one per utilization threshold reached (``utilization_thresholds``)
    - one when latency is at or above ``latency_threshold_ms``
    - one when packet loss is at or above ``loss_threshold``

    The utilization penalty only decreases once utilization has fallen
    ``hysteresis`` below the threshold that raised it, which stops a link from
    flapping between two costs when its load hovers near a threshold.
    """

    utilization_thresholds: tuple[float, ...] = (0.8, 1.0)
    latency_threshold_ms: float = 50.0
    loss_threshold: float = 0.05
    hysteresis: float = 0.1
    max_cost: int = 3

    name = "congestion_aware"

    def __post_init__(self) -> None:
        if self.max_cost < 1:
            raise ValueError("max_cost must be at least 1")
        if list(self.utilization_thresholds) != sorted(self.utilization_thresholds):
            raise ValueError("utilization_thresholds must be ascending")
        if self.hysteresis < 0:
            raise ValueError("hysteresis must not be negative")

    def _utilization_penalty(self, utilization: float) -> int:
        return sum(1 for threshold in self.utilization_thresholds if utilization >= threshold)

    def cost(self, *, utilization: float, latency_ms: float, packet_loss: float, previous: int | None = None) -> int:
        condition_penalty = int(latency_ms >= self.latency_threshold_ms) + int(packet_loss >= self.loss_threshold)
        penalty = self._utilization_penalty(utilization)
        if previous is not None:
            previous_penalty = max(0, previous - 1 - condition_penalty)
            if penalty < previous_penalty:
                # Only step down once load is clearly below the threshold.
                penalty = max(penalty, min(previous_penalty, self._utilization_penalty(utilization + self.hysteresis)))
        return min(self.max_cost, 1 + penalty + condition_penalty)

    def describe(self) -> dict[str, object]:
        return {
            "type": self.name,
            "utilization_thresholds": list(self.utilization_thresholds),
            "latency_threshold_ms": self.latency_threshold_ms,
            "loss_threshold": self.loss_threshold,
            "hysteresis": self.hysteresis,
            "max_cost": self.max_cost,
        }


LinkCostPolicy = HopCountCost | CongestionAwareCost


def cost_policy_from_config(config: dict[str, object] | None) -> LinkCostPolicy:
    """Build a link-cost policy from a scenario's ``metric`` object."""
    if not config:
        return HopCountCost()
    kind = config.get("type", "hop_count")
    if kind == "hop_count":
        return HopCountCost()
    if kind == "congestion_aware":
        defaults = CongestionAwareCost()
        return CongestionAwareCost(
            utilization_thresholds=tuple(config.get("utilization_thresholds", defaults.utilization_thresholds)),
            latency_threshold_ms=float(config.get("latency_threshold_ms", defaults.latency_threshold_ms)),
            loss_threshold=float(config.get("loss_threshold", defaults.loss_threshold)),
            hysteresis=float(config.get("hysteresis", defaults.hysteresis)),
            max_cost=int(config.get("max_cost", defaults.max_cost)),
        )
    raise ValueError("metric.type must be 'hop_count' or 'congestion_aware'")
