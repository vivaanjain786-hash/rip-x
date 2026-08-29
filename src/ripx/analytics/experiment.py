"""Minimal reproducible convergence experiment runner."""

from __future__ import annotations

import json
from pathlib import Path

from ripx.simulation.scenarios import Scenario, load_scenario
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


def run_scenario(path: str | Path) -> dict[str, int | str]:
    """Run one file-backed scenario and include its human-readable identifier."""
    scenario: Scenario = load_scenario(path)
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


def save_result(result: dict[str, int | str], destination: str | Path) -> None:
    Path(destination).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
