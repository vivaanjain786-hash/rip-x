"""Minimal reproducible convergence experiment runner."""

from __future__ import annotations

import json
from pathlib import Path

from ripx.analytics.telemetry import collect_telemetry
from ripx.config import describe_options, network_options, resolve_config
from ripx.analytics.validation import expected_metrics
from ripx.routing.rip import INFINITY
from ripx.simulation.scenarios import FaultEvent, Scenario, load_scenario
from ripx.simulation.topologies import (
    enterprise_like,
    iot_edge_like,
    line,
    mesh,
    random_connected,
    ring,
    scale_free,
    star,
)
from ripx.simulation.traffic import TrafficFlow, simulate_traffic
from ripx.simulation.traffic_engineering import engineer_traffic


FACTORIES = {
    "line": line,
    "ring": ring,
    "star": star,
    "mesh": mesh,
}


def run_convergence_experiment(topology: str, size: int) -> dict[str, int | str]:
    network = FACTORIES[topology](size)
    result = network.converge()
    return {
        "topology": topology,
        "routers": size,
        "convergence_rounds": result.rounds,
        "control_messages": result.control_messages,
    }


def run_bellman_ford_validation(topology: str, size: int) -> dict[str, object]:
    """Compare converged RIP routing tables against standalone Bellman-Ford hop counts.

    Runs the simulator to convergence, then independently computes shortest-hop
    paths from every router using the standalone Bellman-Ford implementation.
    Returns a report listing any destination where the RIP metric differs from
    the Bellman-Ford distance, or an empty ``mismatches`` list when the tables
    are consistent.

    This is the end-to-end correctness check for the RIP simulator baseline.
    """
    network = FACTORIES[topology](size)
    network.converge()
    return {"topology": topology, "routers": size, **validate_against_bellman_ford(network)}


def validate_against_bellman_ford(network) -> dict[str, object]:
    """Compare a network's current RIP metrics with Bellman-Ford over its link costs."""
    expected = expected_metrics(network)
    mismatches: list[dict[str, object]] = []
    for source, row in expected.items():
        for destination, bf_metric in row.items():
            rip_route = network.routers[source].route(destination)
            rip_metric = rip_route.metric if rip_route is not None else None
            if rip_metric == INFINITY and bf_metric is None:
                continue
            if rip_metric != bf_metric:
                mismatches.append(
                    {
                        "source": source,
                        "destination": destination,
                        "rip_metric": rip_metric,
                        "bellman_ford_metric": bf_metric,
                    }
                )
    return {
        "mismatches": mismatches,
        "valid": len(mismatches) == 0,
    }


def run_scenario(path: str | Path) -> dict[str, object]:
    """Run one file-backed scenario and include its human-readable identifier."""
    scenario: Scenario = load_scenario(path)
    if scenario.events or scenario.flows or scenario.rip is not None or scenario.links:
        return run_failure_scenario(scenario)
    topology = scenario.topology
    if topology == "random":
        network = random_connected(
            scenario.routers, seed=scenario.seed, edge_probability=scenario.edge_probability
        )
        convergence = network.converge()
        result: dict[str, int | str] = {
            "topology": "random",
            "routers": scenario.routers,
            "convergence_rounds": convergence.rounds,
            "control_messages": convergence.control_messages,
            "seed": scenario.seed,
        }
    elif topology == "scale_free":
        network = scale_free(
            scenario.routers, seed=scenario.seed, initial_clique=scenario.initial_clique
        )
        convergence = network.converge()
        result = {
            "topology": "scale_free",
            "routers": scenario.routers,
            "convergence_rounds": convergence.rounds,
            "control_messages": convergence.control_messages,
            "seed": scenario.seed,
        }
    elif topology == "enterprise":
        network = enterprise_like()
        convergence = network.converge()
        result = {
            "topology": "enterprise",
            "routers": scenario.routers,
            "convergence_rounds": convergence.rounds,
            "control_messages": convergence.control_messages,
        }
    elif topology == "iot_edge":
        network = iot_edge_like(
            edge_hubs=scenario.edge_hubs, devices_per_hub=scenario.devices_per_hub
        )
        convergence = network.converge()
        result = {
            "topology": "iot_edge",
            "routers": scenario.routers,
            "convergence_rounds": convergence.rounds,
            "control_messages": convergence.control_messages,
        }
    else:
        result = run_convergence_experiment(topology, scenario.routers)
    return {"scenario": scenario.name, **result}


def _build_network(scenario: Scenario, options: dict[str, object] | None = None):
    options = options if options is not None else network_options(scenario.rip)
    topology = scenario.topology
    if topology == "random":
        network = random_connected(
            scenario.routers, seed=scenario.seed, edge_probability=scenario.edge_probability, **options
        )
    elif topology == "scale_free":
        network = scale_free(
            scenario.routers, seed=scenario.seed, initial_clique=scenario.initial_clique, **options
        )
    elif topology == "enterprise":
        network = enterprise_like(**options)
    elif topology == "iot_edge":
        network = iot_edge_like(
            edge_hubs=scenario.edge_hubs, devices_per_hub=scenario.devices_per_hub, **options
        )
    else:
        network = FACTORIES[topology](scenario.routers, **options)
    for spec in scenario.links:
        network.configure_link(*spec.link, **spec.properties())
    return network


def _apply_event(network, event: FaultEvent) -> None:
    if event.type == "router_failure":
        network.fail_router(event.router)
    elif event.type == "router_recovery":
        network.recover_router(event.router)
    elif event.type == "link_failure":
        network.fail_link(*event.link)
    elif event.type == "link_recovery":
        network.recover_link(*event.link)
    elif event.type == "latency_spike":
        network.set_link_conditions(*event.link, latency_ms=event.latency_ms)
    elif event.type == "packet_loss_spike":
        network.set_link_conditions(*event.link, packet_loss=event.packet_loss)
    elif event.type == "link_restore":
        network.restore_link_conditions(*event.link)


def run_failure_scenario(scenario: Scenario) -> dict[str, object]:
    """Measure baseline and re-convergence with optional traffic telemetry."""
    options = network_options(scenario.rip)
    network = _build_network(scenario, options)
    baseline = network.converge()
    flows = [TrafficFlow(flow.source, flow.destination, flow.rate_mbps) for flow in scenario.flows]
    engineering = scenario.traffic_engineering
    phases = [_measure_phase(network, "baseline", baseline.rounds, baseline.control_messages, flows, engineering)]
    for event in scenario.events:
        _apply_event(network, event)
        convergence = network.converge()
        target = event.router if event.router is not None else "-".join(event.link)
        phase = _measure_phase(
            network, event.type, convergence.rounds, convergence.control_messages, flows, engineering
        )
        phase["target"] = target
        phases.append(phase)
    result: dict[str, object] = {
        "scenario": scenario.name,
        "topology": scenario.topology,
        "routers": scenario.routers,
    }
    if scenario.rip is not None:
        result["rip"] = describe_options(options, resolve_config(scenario.rip)["profile"])
    result["phases"] = phases
    return result


def _measure_phase(
    network,
    event: str,
    rounds: int,
    messages: int,
    flows: list[TrafficFlow],
    engineering: dict[str, object] | None = None,
) -> dict[str, object]:
    """Collect routing telemetry and optional traffic metrics for one phase."""
    engineered = None
    if flows and engineering is not None:
        engineered = engineer_traffic(
            network,
            flows,
            max_epochs=int(engineering.get("max_epochs", 10)),
            max_rounds=int(engineering.get("max_rounds", 200)),
        )
    traffic = simulate_traffic(network, flows) if flows else None
    phase: dict[str, object] = {
        "event": event,
        "convergence_rounds": rounds,
        "control_messages": messages,
        "telemetry": collect_telemetry(network, traffic),
    }
    if engineered is not None:
        phase["traffic_engineering"] = engineered.summary()
    if traffic is not None:
        phase["traffic"] = {
            "offered_mbps": sum(flow.rate_mbps for flow in flows),
            "delivered_mbps": traffic.delivered_mbps,
            "dropped_mbps": traffic.dropped_mbps,
            "unroutable_mbps": traffic.unroutable_mbps,
            "maximum_utilization": traffic.maximum_utilization,
            "bottleneck_links": traffic.bottleneck_links,
            "link_utilization": traffic.link_utilization,
        }
    return phase


def save_result(result: dict[str, object], destination: str | Path) -> None:
    Path(destination).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
