"""Minimal reproducible convergence experiment runner."""

from __future__ import annotations

import json
from pathlib import Path

from ripx.analytics.telemetry import collect_telemetry
from ripx.simulation.scenarios import FaultEvent, Scenario, load_scenario
from ripx.simulation.topologies import line, mesh, random_connected, ring, star
from ripx.simulation.traffic import TrafficFlow, simulate_traffic


FACTORIES = {"line": line, "ring": ring, "star": star, "mesh": mesh}


def run_convergence_experiment(topology: str, size: int) -> dict[str, int | str]:
    network = FACTORIES[topology](size)
    result = network.converge()
    return {
        "topology": topology,
        "routers": size,
        "convergence_rounds": result.rounds,
        "control_messages": result.control_messages,
    }


def run_scenario(path: str | Path) -> dict[str, object]:
    """Run one file-backed scenario and include its human-readable identifier."""
    scenario: Scenario = load_scenario(path)
    if scenario.events or scenario.flows:
        return run_failure_scenario(scenario)
    if scenario.topology == "random":
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
    else:
        result = run_convergence_experiment(scenario.topology, scenario.routers)
    return {"scenario": scenario.name, **result}


def _build_network(scenario: Scenario):
    if scenario.topology == "random":
        return random_connected(
            scenario.routers, seed=scenario.seed, edge_probability=scenario.edge_probability
        )
    return FACTORIES[scenario.topology](scenario.routers)


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
    network = _build_network(scenario)
    baseline = network.converge()
    flows = [TrafficFlow(flow.source, flow.destination, flow.rate_mbps) for flow in scenario.flows]
    phases = [_measure_phase(network, "baseline", baseline.rounds, baseline.control_messages, flows)]
    for event in scenario.events:
        _apply_event(network, event)
        convergence = network.converge()
        target = event.router if event.router is not None else "-".join(event.link)
        phase = _measure_phase(network, event.type, convergence.rounds, convergence.control_messages, flows)
        phase["target"] = target
        phases.append(phase)
    return {
        "scenario": scenario.name,
        "topology": scenario.topology,
        "routers": scenario.routers,
        "phases": phases,
    }


def _measure_phase(network, event: str, rounds: int, messages: int, flows: list[TrafficFlow]) -> dict[str, object]:
    """Collect routing telemetry and optional traffic metrics for one phase."""
    traffic = simulate_traffic(network, flows) if flows else None
    phase: dict[str, object] = {
        "event": event,
        "convergence_rounds": rounds,
        "control_messages": messages,
        "telemetry": collect_telemetry(network, traffic),
    }
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
