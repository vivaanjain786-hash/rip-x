"""Minimal reproducible convergence experiment runner."""

from __future__ import annotations

import json
from pathlib import Path

from ripx.simulation.scenarios import FaultEvent, Scenario, load_scenario
from ripx.simulation.topologies import line, mesh, random_connected, ring, star


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
    if scenario.events:
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


def run_failure_scenario(scenario: Scenario) -> dict[str, object]:
    """Measure baseline and re-convergence after each configured fault event."""
    network = _build_network(scenario)
    baseline = network.converge()
    phases: list[dict[str, int | str]] = [
        {"event": "baseline", "convergence_rounds": baseline.rounds, "control_messages": baseline.control_messages}
    ]
    for event in scenario.events:
        _apply_event(network, event)
        convergence = network.converge()
        target = event.router if event.router is not None else "-".join(event.link)
        phases.append(
            {
                "event": event.type,
                "target": target,
                "convergence_rounds": convergence.rounds,
                "control_messages": convergence.control_messages,
            }
        )
    return {
        "scenario": scenario.name,
        "topology": scenario.topology,
        "routers": scenario.routers,
        "phases": phases,
    }


def save_result(result: dict[str, object], destination: str | Path) -> None:
    Path(destination).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
