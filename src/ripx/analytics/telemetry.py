"""Structured measurements from the current RIP-X simulator state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ripx.simulation.network import RipNetwork

if TYPE_CHECKING:
    from ripx.simulation.traffic import TrafficReport


def collect_telemetry(network: RipNetwork, traffic: TrafficReport | None = None) -> dict[str, object]:
    """Return factual link and routing-table state for an experiment phase."""
    reachable_metrics: list[int] = []
    unreachable_routes = 0
    for router_name, router in network.routers.items():
        if router_name in network.failed_routers:
            continue
        for destination, route in router.routes.items():
            if destination == router_name:
                continue
            if route.reachable:
                reachable_metrics.append(route.metric)
            else:
                unreachable_routes += 1

    utilization = traffic.link_utilization if traffic is not None else {}
    links = []
    for link in sorted(network.links.values(), key=lambda item: (item.left, item.right)):
        label = "-".join(sorted((link.left, link.right)))
        links.append(
            {
                "link": label,
                "up": link.up and link.left not in network.failed_routers and link.right not in network.failed_routers,
                "bandwidth_mbps": link.bandwidth_mbps,
                "latency_ms": link.latency_ms,
                "configured_packet_loss": link.packet_loss,
                "utilization": utilization.get(label),
            }
        )
    return {
        "simulation_round": network.now,
        "active_routers": len(network.routers) - len(network.failed_routers),
        "failed_routers": sorted(network.failed_routers),
        "reachable_routes": len(reachable_metrics),
        "unreachable_routes": unreachable_routes,
        "average_reachable_hops": sum(reachable_metrics) / len(reachable_metrics) if reachable_metrics else None,
        "route_changes_total": sum(router.route_change_count for router in network.routers.values()),
        "links": links,
    }
