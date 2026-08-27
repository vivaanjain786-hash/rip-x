"""Minimal reproducible convergence experiment runner."""

from __future__ import annotations

import json
from pathlib import Path

from ripx.simulation.topologies import line, ring, star


FACTORIES = {"line": line, "ring": ring, "star": star}


def run_convergence_experiment(topology: str, size: int) -> dict[str, int | str]:
    network = FACTORIES[topology](size)
    result = network.converge()
    return {
        "topology": topology,
        "routers": size,
        "convergence_rounds": result.rounds,
        "control_messages": result.control_messages,
    }


def save_result(result: dict[str, int | str], destination: str | Path) -> None:
    Path(destination).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
