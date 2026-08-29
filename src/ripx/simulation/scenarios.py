"""Scenario loading for repeatable RIP-X experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Scenario:
    name: str
    topology: str
    routers: int
    seed: int = 0
    edge_probability: float = 0.25


def load_scenario(path: str | Path) -> Scenario:
    """Load and validate a small JSON scenario for a baseline experiment."""
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON in {source}: {error.msg}") from error
    required = {"name", "topology", "routers"}
    missing = required.difference(data)
    if missing:
        raise ValueError(f"scenario is missing required fields: {', '.join(sorted(missing))}")
    if data["topology"] not in {"line", "ring", "star", "mesh", "random"}:
        raise ValueError("baseline topology must be one of: line, ring, star, mesh, random")
    if not isinstance(data["routers"], int) or data["routers"] < 2:
        raise ValueError("routers must be an integer of at least 2")
    if not isinstance(data["name"], str) or not data["name"].strip():
        raise ValueError("name must be a non-empty string")
    seed = data.get("seed", 0)
    probability = data.get("edge_probability", 0.25)
    if not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if not isinstance(probability, (int, float)) or not 0 <= probability <= 1:
        raise ValueError("edge_probability must be between 0 and 1")
    return Scenario(data["name"], data["topology"], data["routers"], seed, float(probability))
