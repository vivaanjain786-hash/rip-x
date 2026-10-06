"""RIP-X traffic engineering: steer flows away from congested links.

The loop measures traffic on the current RIP routes, raises the cost of links
whose utilization crosses the congestion-aware thresholds, lets RIP
re-converge, and measures again. Costs only rise within one run, so the loop
always ends: each link's cost is bounded by the policy's ``max_cost``. The
epoch with the best measured outcome (most delivered traffic, then lowest
peak utilization) is installed at the end and measured again. Epoch 0 is
plain RIP routing, so it is always a candidate; when RIP breaks a metric tie
differently after reinstalling costs, the final measurement is what is
reported.
"""

from __future__ import annotations

from dataclasses import dataclass

from ripx.routing.metrics import CongestionAwareCost
from ripx.simulation.network import RipNetwork
from ripx.simulation.traffic import TrafficFlow, TrafficReport, simulate_traffic


@dataclass(frozen=True)
class TrafficEngineeringResult:
    initial: TrafficReport
    final: TrafficReport
    epochs: list[dict[str, object]]
    selected_epoch: int
    convergence_rounds: int
    control_messages: int
    converged: bool

    def summary(self) -> dict[str, object]:
        return {
            "epochs": self.epochs,
            "selected_epoch": self.selected_epoch,
            "convergence_rounds": self.convergence_rounds,
            "control_messages": self.control_messages,
            "converged": self.converged,
            "delivered_mbps_before": self.initial.delivered_mbps,
            "delivered_mbps_after": self.final.delivered_mbps,
            "maximum_utilization_before": self.initial.maximum_utilization,
            "maximum_utilization_after": self.final.maximum_utilization,
        }


def _utilization_by_key(network: RipNetwork, report: TrafficReport) -> dict[frozenset[str], float]:
    by_label = {"-".join(sorted(key)): key for key in network.links}
    return {by_label[label]: value for label, value in report.link_utilization.items()}


def _epoch_record(epoch: int, report: TrafficReport, rounds: int, messages: int, raised: list[frozenset[str]]) -> dict[str, object]:
    return {
        "epoch": epoch,
        "delivered_mbps": report.delivered_mbps,
        "maximum_utilization": report.maximum_utilization,
        "bottleneck_links": report.bottleneck_links,
        "raised_links": sorted("-".join(sorted(key)) for key in raised),
        "convergence_rounds": rounds,
        "control_messages": messages,
    }


def engineer_traffic(
    network: RipNetwork,
    flows: list[TrafficFlow],
    *,
    max_epochs: int = 10,
    max_rounds: int = 200,
) -> TrafficEngineeringResult:
    """Run the traffic-engineering loop on ``network`` and leave the best costs installed."""
    policy = network.cost_policy
    if not isinstance(policy, CongestionAwareCost):
        raise ValueError("traffic engineering needs the congestion_aware metric")
    if max_epochs < 0:
        raise ValueError("max_epochs must not be negative")

    # Start every run from load-free costs, so epoch 0 is plain RIP routing
    # (with latency and loss penalties only) for the current topology.
    network.link_utilization = {}
    network.set_link_costs(
        {
            key: policy.cost(utilization=0.0, latency_ms=link.latency_ms, packet_loss=link.packet_loss)
            for key, link in network.links.items()
        }
    )
    convergence = network.converge(max_rounds)
    total_rounds = convergence.rounds
    total_messages = convergence.control_messages
    converged = not convergence.changed
    report = simulate_traffic(network, flows)
    initial = report
    history: list[tuple[TrafficReport, dict[frozenset[str], int]]] = [(report, dict(network.link_costs))]
    epochs = [_epoch_record(0, report, 0, 0, [])]

    for epoch in range(1, max_epochs + 1):
        utilization = _utilization_by_key(network, report)
        raised_costs: dict[frozenset[str], int] = {}
        for key, current in network.link_costs.items():
            link = network.links[key]
            proposed = policy.cost(
                utilization=utilization.get(key, 0.0),
                latency_ms=link.latency_ms,
                packet_loss=link.packet_loss,
                previous=current,
            )
            if proposed > current:
                raised_costs[key] = proposed
        if not raised_costs:
            break
        network.set_link_costs(raised_costs)
        convergence = network.converge(max_rounds)
        total_rounds += convergence.rounds
        total_messages += convergence.control_messages
        converged = converged and not convergence.changed
        report = simulate_traffic(network, flows)
        history.append((report, dict(network.link_costs)))
        epochs.append(_epoch_record(epoch, report, convergence.rounds, convergence.control_messages, list(raised_costs)))

    selected = min(
        range(len(history)),
        key=lambda index: (-round(history[index][0].delivered_mbps, 9), history[index][0].maximum_utilization, index),
    )
    if selected != len(history) - 1:
        network.set_link_costs(history[selected][1])
        convergence = network.converge(max_rounds)
        total_rounds += convergence.rounds
        total_messages += convergence.control_messages
        converged = converged and not convergence.changed
        report = simulate_traffic(network, flows)
    network.link_utilization = _utilization_by_key(network, report)
    return TrafficEngineeringResult(
        initial=initial,
        final=report,
        epochs=epochs,
        selected_epoch=selected,
        convergence_rounds=total_rounds,
        control_messages=total_messages,
        converged=converged,
    )
