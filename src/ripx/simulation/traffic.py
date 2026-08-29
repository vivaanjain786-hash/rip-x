"""Deterministic traffic accounting over current RIP forwarding paths."""

from __future__ import annotations

from dataclasses import dataclass

from ripx.simulation.network import RipNetwork


@dataclass(frozen=True)
class TrafficFlow:
    source: str
    destination: str
    rate_mbps: float


@dataclass(frozen=True)
class TrafficReport:
    link_utilization: dict[str, float]
    flow_paths: dict[str, list[str] | None]
    delivered_mbps: float
    dropped_mbps: float
    unroutable_mbps: float


def simulate_traffic(network: RipNetwork, flows: list[TrafficFlow]) -> TrafficReport:
    """Measure offered traffic against current routes and link capacities.

    This is an accounting model, not a packet-level emulator. Traffic offered
    to a missing route is unroutable. For a routed flow, configured link loss
    and capacity oversubscription determine the delivered amount.
    """
    loads: dict[frozenset[str], float] = {key: 0.0 for key in network.links}
    paths: dict[str, list[str] | None] = {}
    routed: list[tuple[TrafficFlow, list[str]]] = []
    unroutable = 0.0
    for index, flow in enumerate(flows, start=1):
        if flow.rate_mbps < 0:
            raise ValueError("traffic flow rate must not be negative")
        path = network.route_path(flow.source, flow.destination)
        flow_key = f"flow-{index}:{flow.source}->{flow.destination}"
        paths[flow_key] = path
        if path is None:
            unroutable += flow.rate_mbps
            continue
        routed.append((flow, path))
        for left, right in zip(path, path[1:]):
            loads[frozenset((left, right))] += flow.rate_mbps

    utilization = {
        "-".join(sorted(link_key)): load / network.links[link_key].bandwidth_mbps
        for link_key, load in loads.items()
        if network.links[link_key].up
    }
    delivered = 0.0
    for flow, path in routed:
        delivery_ratio = 1.0
        for left, right in zip(path, path[1:]):
            link_key = frozenset((left, right))
            link = network.links[link_key]
            delivery_ratio *= 1 - link.packet_loss
            if loads[link_key] > link.bandwidth_mbps:
                delivery_ratio *= link.bandwidth_mbps / loads[link_key]
        delivered += flow.rate_mbps * delivery_ratio
    offered = sum(flow.rate_mbps for flow in flows)
    return TrafficReport(utilization, paths, delivered, offered - delivered, unroutable)
