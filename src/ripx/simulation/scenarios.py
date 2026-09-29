"""Scenario loading for repeatable RIP-X experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ripx.config import resolve_config


@dataclass(frozen=True)
class FaultEvent:
    type: str
    router: str | None = None
    link: tuple[str, str] | None = None
    latency_ms: float | None = None
    packet_loss: float | None = None


@dataclass(frozen=True)
class FlowSpec:
    source: str
    destination: str
    rate_mbps: float


@dataclass(frozen=True)
class LinkSpec:
    link: tuple[str, str]
    bandwidth_mbps: float | None = None
    latency_ms: float | None = None
    packet_loss: float | None = None

    def properties(self) -> dict[str, float]:
        values = {
            "bandwidth_mbps": self.bandwidth_mbps,
            "latency_ms": self.latency_ms,
            "packet_loss": self.packet_loss,
        }
        return {key: value for key, value in values.items() if value is not None}


@dataclass(frozen=True)
class Scenario:
    name: str
    topology: str
    routers: int
    seed: int = 0
    edge_probability: float = 0.25
    # scale_free
    initial_clique: int = 3
    # iot_edge_like
    edge_hubs: int = 3
    devices_per_hub: int = 4
    events: tuple[FaultEvent, ...] = ()
    flows: tuple[FlowSpec, ...] = ()
    links: tuple[LinkSpec, ...] = ()
    # RIP / RIP-X settings (see ripx.config); None keeps the baseline defaults.
    rip: dict[str, Any] | None = None
    # Run the RIP-X traffic-engineering loop after each phase's convergence.
    traffic_engineering: dict[str, Any] | None = None


_VALID_TOPOLOGIES = {"line", "ring", "star", "mesh", "random", "scale_free", "enterprise", "iot_edge"}


def load_scenario(path: str | Path) -> Scenario:
    """Load and validate a JSON scenario for a baseline experiment."""
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON in {source}: {error.msg}") from error
    topology = data.get("topology", "")
    if topology not in _VALID_TOPOLOGIES:
        raise ValueError(
            f"baseline topology must be one of: {', '.join(sorted(_VALID_TOPOLOGIES))}"
        )
    required = {"name", "topology"}
    # enterprise has a fixed size; iot_edge derives size from hubs × devices
    if topology not in {"enterprise", "iot_edge"}:
        required.add("routers")
    missing = required.difference(data)
    if missing:
        raise ValueError(f"scenario is missing required fields: {', '.join(sorted(missing))}")
    if not isinstance(data["name"], str) or not data["name"].strip():
        raise ValueError("name must be a non-empty string")
    # Derive router count for fixed topologies
    if topology == "enterprise":
        routers = 10  # 2 core + 3 dist + 5 access
    elif topology == "iot_edge":
        edge_hubs = data.get("edge_hubs", 3)
        devices_per_hub = data.get("devices_per_hub", 4)
        if not isinstance(edge_hubs, int) or edge_hubs < 1:
            raise ValueError("edge_hubs must be a positive integer")
        if not isinstance(devices_per_hub, int) or devices_per_hub < 1:
            raise ValueError("devices_per_hub must be a positive integer")
        routers = 1 + edge_hubs + edge_hubs * devices_per_hub
    else:
        routers = data["routers"]
        if not isinstance(routers, int) or routers < 2:
            raise ValueError("routers must be an integer of at least 2")
    seed = data.get("seed", 0)
    probability = data.get("edge_probability", 0.25)
    if not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if not isinstance(probability, (int, float)) or not 0 <= probability <= 1:
        raise ValueError("edge_probability must be between 0 and 1")
    initial_clique = data.get("initial_clique", 3)
    if not isinstance(initial_clique, int) or initial_clique < 1:
        raise ValueError("initial_clique must be a positive integer")
    edge_hubs = data.get("edge_hubs", 3)
    devices_per_hub = data.get("devices_per_hub", 4)
    events_data = data.get("events", [])
    if not isinstance(events_data, list):
        raise ValueError("events must be a list")
    events: list[FaultEvent] = []
    for index, event in enumerate(events_data):
        if not isinstance(event, dict):
            raise ValueError(f"event {index} must be an object")
        event_type = event.get("type")
        if event_type in {"router_failure", "router_recovery"}:
            router = event.get("router")
            if not isinstance(router, str) or not router:
                raise ValueError(f"event {index} requires a router name")
            events.append(FaultEvent(event_type, router=router))
        elif event_type in {"link_failure", "link_recovery", "latency_spike", "packet_loss_spike", "link_restore"}:
            link = event.get("link")
            if not isinstance(link, list) or len(link) != 2 or not all(isinstance(node, str) for node in link):
                raise ValueError(f"event {index} requires a two-router link")
            if event_type == "latency_spike":
                latency = event.get("latency_ms")
                if not isinstance(latency, (int, float)) or latency < 0:
                    raise ValueError(f"event {index} requires a non-negative latency_ms")
                events.append(FaultEvent(event_type, link=(link[0], link[1]), latency_ms=float(latency)))
            elif event_type == "packet_loss_spike":
                loss = event.get("packet_loss")
                if not isinstance(loss, (int, float)) or not 0 <= loss <= 1:
                    raise ValueError(f"event {index} requires packet_loss between 0 and 1")
                events.append(FaultEvent(event_type, link=(link[0], link[1]), packet_loss=float(loss)))
            else:
                events.append(FaultEvent(event_type, link=(link[0], link[1])))
        else:
            raise ValueError(f"event {index} has an unsupported type")
    flows_data = data.get("flows", [])
    if not isinstance(flows_data, list):
        raise ValueError("flows must be a list")
    flows: list[FlowSpec] = []
    for index, flow in enumerate(flows_data):
        if not isinstance(flow, dict):
            raise ValueError(f"flow {index} must be an object")
        source, destination, rate = flow.get("source"), flow.get("destination"), flow.get("rate_mbps")
        if not isinstance(source, str) or not isinstance(destination, str):
            raise ValueError(f"flow {index} requires source and destination routers")
        if not isinstance(rate, (int, float)) or rate < 0:
            raise ValueError(f"flow {index} requires a non-negative rate_mbps")
        flows.append(FlowSpec(source, destination, float(rate)))
    links: list[LinkSpec] = []
    links_data = data.get("links", [])
    if not isinstance(links_data, list):
        raise ValueError("links must be a list")
    for index, entry in enumerate(links_data):
        if not isinstance(entry, dict):
            raise ValueError(f"link {index} must be an object")
        link = entry.get("link")
        if not isinstance(link, list) or len(link) != 2 or not all(isinstance(node, str) for node in link):
            raise ValueError(f"link {index} requires a two-router link")
        bandwidth = entry.get("bandwidth_mbps")
        latency = entry.get("latency_ms")
        loss = entry.get("packet_loss")
        if bandwidth is not None and (not isinstance(bandwidth, (int, float)) or bandwidth <= 0):
            raise ValueError(f"link {index} bandwidth_mbps must be positive")
        if latency is not None and (not isinstance(latency, (int, float)) or latency < 0):
            raise ValueError(f"link {index} latency_ms must not be negative")
        if loss is not None and (not isinstance(loss, (int, float)) or not 0 <= loss <= 1):
            raise ValueError(f"link {index} packet_loss must be between 0 and 1")
        links.append(
            LinkSpec(
                (link[0], link[1]),
                None if bandwidth is None else float(bandwidth),
                None if latency is None else float(latency),
                None if loss is None else float(loss),
            )
        )
    rip = data.get("rip")
    if rip is not None:
        if not isinstance(rip, dict):
            raise ValueError("rip must be an object")
        resolve_config(rip)
    traffic_engineering = data.get("traffic_engineering")
    if traffic_engineering is not None and not isinstance(traffic_engineering, dict):
        raise ValueError("traffic_engineering must be an object")
    return Scenario(
        name=data["name"],
        topology=data["topology"],
        routers=routers,
        seed=seed,
        edge_probability=float(probability),
        initial_clique=initial_clique,
        edge_hubs=edge_hubs,
        devices_per_hub=devices_per_hub,
        events=tuple(events),
        flows=tuple(flows),
        links=tuple(links),
        rip=rip,
        traffic_engineering=traffic_engineering,
    )
