"""Controlled benchmark of standard RIP against RIP-X.

Two experiments, each run over many seeds with every configuration seeing the
same topology, the same failure timeline and the same traffic:

1. **Update control** (``run_update_benchmark``): a fixed timeline of stable
   periods, a link failure and recovery, and a router failure and recovery.
   Every round the routing tables are checked against Bellman-Ford, so
   convergence, black holes and loops are measured, not inferred.
2. **Traffic engineering** (``run_traffic_benchmark``): random flows on a
   topology with mixed link capacities, delivered under hop-count RIP and
   under the RIP-X traffic-engineering loop.

Summaries report the mean, a 95% confidence interval, and paired differences
against standard RIP. Every number comes from running the simulator.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any, Callable

from ripx.analytics.validation import expected_metrics, routing_state
from ripx.config import network_options
from ripx.simulation.network import RipNetwork
from ripx.simulation.topologies import random_connected
from ripx.simulation.traffic import TrafficFlow, simulate_traffic
from ripx.simulation.traffic_engineering import engineer_traffic

# Configurations compared in the update-control benchmark. "rip" is the
# baseline; the two ablations show what each RIP-X part contributes.
UPDATE_CONFIGURATIONS: dict[str, dict[str, Any]] = {
    "rip": {"profile": "rip"},
    "rip+requests": {"profile": "rip", "request_on_loss": True},
    "adaptive-only": {"profile": "ripx", "request_on_loss": False},
    "ripx": {"profile": "ripx"},
}

# Two-sided 95% Student-t critical values by degrees of freedom.
_T_95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262,
    10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110,
    18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980,
}


def _t_critical(df: int) -> float:
    if df in _T_95:
        return _T_95[df]
    for bound in (40, 60, 120):
        if df < bound:
            return _T_95[bound]
    return 1.960


def describe_sample(values: list[float]) -> dict[str, float | int]:
    """Mean, standard deviation and 95% confidence interval of a sample."""
    count = len(values)
    mean = statistics.fmean(values) if values else float("nan")
    if count < 2:
        return {"n": count, "mean": mean, "stdev": 0.0, "ci95_low": mean, "ci95_high": mean}
    stdev = statistics.stdev(values)
    margin = _t_critical(count - 1) * stdev / count**0.5
    return {"n": count, "mean": mean, "stdev": stdev, "ci95_low": mean - margin, "ci95_high": mean + margin}


@dataclass(frozen=True)
class Timeline:
    """Rounds (after initial convergence) at which each event is applied."""

    link_failure: int = 100
    link_recovery: int = 200
    router_failure: int = 300
    router_recovery: int = 400
    horizon: int = 500

    def events(self) -> list[tuple[int, str]]:
        return [
            (self.link_failure, "link_failure"),
            (self.link_recovery, "link_recovery"),
            (self.router_failure, "router_failure"),
            (self.router_recovery, "router_recovery"),
        ]


def _graph_connected(nodes: set[str], edges: list[tuple[str, str]]) -> bool:
    if not nodes:
        return True
    adjacency: dict[str, set[str]] = {node: set() for node in nodes}
    for left, right in edges:
        if left in nodes and right in nodes:
            adjacency[left].add(right)
            adjacency[right].add(left)
    start = next(iter(nodes))
    seen = {start}
    frontier = [start]
    while frontier:
        node = frontier.pop()
        for neighbor in adjacency[node] - seen:
            seen.add(neighbor)
            frontier.append(neighbor)
    return seen == nodes


def choose_failures(network: RipNetwork, seed: int) -> tuple[tuple[str, str], str]:
    """Pick a link and a router whose loss leaves the rest of the network connected.

    The choice depends only on the topology and seed, so every configuration
    sees the same failures.
    """
    generator = Random(seed * 7919 + 17)
    nodes = set(network.routers)
    edges = sorted(tuple(sorted(key)) for key in network.links)
    links = [edge for edge in edges if _graph_connected(nodes, [other for other in edges if other != edge])]
    routers = sorted(
        router
        for router in nodes
        if len(network.neighbors(router)) >= 2
        and _graph_connected(nodes - {router}, [edge for edge in edges if router not in edge])
    )
    if not links or not routers:
        raise ValueError("topology has no failure that keeps the network connected")
    return generator.choice(links), generator.choice(routers)


def run_update_trial(
    config: dict[str, Any],
    *,
    seed: int,
    routers: int = 20,
    edge_probability: float = 0.15,
    timeline: Timeline = Timeline(),
    series: bool = False,
) -> dict[str, Any]:
    """Run one configuration on one seeded topology and measure every round.

    With ``series=True`` the result also carries per-round counters for charts.
    """
    network = random_connected(routers, seed=seed, edge_probability=edge_probability, **network_options(config))
    failed_link, failed_router = choose_failures(network, seed)
    initial = network.converge(max_rounds=500)
    if initial.changed:
        raise RuntimeError("initial convergence did not finish")

    events = dict(timeline.events())
    expected = expected_metrics(network)
    changes_at_start = sum(router.route_change_count for router in network.routers.values())
    messages_by_round: list[int] = []
    incorrect_rounds: list[bool] = []
    blackhole_pair_rounds = 0
    loop_pair_rounds = 0
    stale_pair_rounds = 0
    blackholes_by_phase = {"stable": 0, **{name: 0 for _, name in timeline.events()}}
    phase = "stable"
    per_round: list[dict[str, int]] = []
    for round_index in range(timeline.horizon):
        event = events.get(round_index)
        if event == "link_failure":
            network.fail_link(*failed_link)
        elif event == "link_recovery":
            network.recover_link(*failed_link)
        elif event == "router_failure":
            network.fail_router(failed_router)
        elif event == "router_recovery":
            network.recover_router(failed_router)
        if event is not None:
            expected = expected_metrics(network)
            phase = event
        messages_by_round.append(network.step().control_messages)
        state = routing_state(network, expected)
        incorrect_rounds.append(state["incorrect"] > 0)
        blackhole_pair_rounds += state["blackhole"]
        blackholes_by_phase[phase] += state["blackhole"]
        loop_pair_rounds += state["loop"]
        stale_pair_rounds += state["stale"]
        if series:
            per_round.append(
                {
                    "round": round_index,
                    "messages": sum(messages_by_round),
                    "incorrect": state["incorrect"],
                    "blackhole": state["blackhole"],
                    "loop": state["loop"],
                }
            )

    # Convergence after an event: rounds until the tables match Bellman-Ford
    # and stay matching until the next event (or the end of the run).
    boundaries = [start for start, _ in timeline.events()] + [timeline.horizon]
    convergence: dict[str, int | None] = {}
    for (start, name), end in zip(timeline.events(), boundaries[1:]):
        window = incorrect_rounds[start:end]
        if window and window[-1]:
            convergence[name] = None  # still wrong when the next event arrived
        else:
            last_wrong = max((index for index, wrong in enumerate(window) if wrong), default=-1)
            convergence[name] = last_wrong + 1

    stable_window = messages_by_round[: timeline.link_failure]
    result = {
        "seed": seed,
        "failed_link": "-".join(failed_link),
        "failed_router": failed_router,
        "initial_convergence_rounds": initial.rounds,
        "initial_control_messages": initial.control_messages,
        "control_messages": sum(messages_by_round),
        "stable_control_messages": sum(stable_window),
        "convergence_rounds": convergence,
        "incorrect_rounds": sum(incorrect_rounds),
        "blackhole_pair_rounds": blackhole_pair_rounds,
        "blackhole_pair_rounds_by_phase": blackholes_by_phase,
        "loop_pair_rounds": loop_pair_rounds,
        "stale_pair_rounds": stale_pair_rounds,
        "route_changes": sum(router.route_change_count for router in network.routers.values()) - changes_at_start,
    }
    if series:
        result["series"] = per_round
    return result


_UPDATE_METRICS: dict[str, Callable[[dict[str, Any]], float | None]] = {
    "control_messages": lambda trial: trial["control_messages"],
    "stable_control_messages": lambda trial: trial["stable_control_messages"],
    "link_failure_convergence_rounds": lambda trial: trial["convergence_rounds"]["link_failure"],
    "link_recovery_convergence_rounds": lambda trial: trial["convergence_rounds"]["link_recovery"],
    "router_failure_convergence_rounds": lambda trial: trial["convergence_rounds"]["router_failure"],
    "router_recovery_convergence_rounds": lambda trial: trial["convergence_rounds"]["router_recovery"],
    "incorrect_rounds": lambda trial: trial["incorrect_rounds"],
    "blackhole_pair_rounds": lambda trial: trial["blackhole_pair_rounds"],
    "loop_pair_rounds": lambda trial: trial["loop_pair_rounds"],
    "stale_pair_rounds": lambda trial: trial["stale_pair_rounds"],
    "route_changes": lambda trial: trial["route_changes"],
}


def _summarize(
    trials: dict[str, list[dict[str, Any]]],
    metrics: dict[str, Callable[[dict[str, Any]], float | None]],
    baseline: str,
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for name, runs in trials.items():
        per_metric: dict[str, Any] = {}
        for metric, extract in metrics.items():
            values = [extract(run) for run in runs]
            measured = [float(value) for value in values if value is not None]
            per_metric[metric] = describe_sample(measured)
            per_metric[metric]["unconverged_trials"] = len(values) - len(measured)
            if name != baseline:
                pairs = [
                    (extract(run), extract(base))
                    for run, base in zip(runs, trials[baseline])
                    if extract(run) is not None and extract(base) is not None
                ]
                differences = [float(value - base) for value, base in pairs]
                per_metric[metric]["paired_difference_vs_" + baseline] = describe_sample(differences)
        summary[name] = per_metric
    return summary


def run_update_benchmark(
    seeds: list[int],
    *,
    routers: int = 20,
    edge_probability: float = 0.15,
    configurations: dict[str, dict[str, Any]] | None = None,
    timeline: Timeline = Timeline(),
) -> dict[str, Any]:
    configurations = configurations or UPDATE_CONFIGURATIONS
    trials = {
        name: [
            run_update_trial(config, seed=seed, routers=routers, edge_probability=edge_probability, timeline=timeline)
            for seed in seeds
        ]
        for name, config in configurations.items()
    }
    return {
        "experiment": "update_control",
        "topology": {"type": "random", "routers": routers, "edge_probability": edge_probability},
        "timeline": timeline.__dict__,
        "seeds": seeds,
        "configurations": configurations,
        "summary": _summarize(trials, _UPDATE_METRICS, "rip"),
        "trials": trials,
    }


def _traffic_network(seed: int, routers: int, edge_probability: float, config: dict[str, Any]) -> RipNetwork:
    network = random_connected(routers, seed=seed, edge_probability=edge_probability, **network_options(config))
    generator = Random(seed * 104729 + 3)
    for key in sorted(network.links, key=sorted):
        network.configure_link(*sorted(key), bandwidth_mbps=generator.choice([50.0, 100.0, 200.0]))
    return network


def _random_flows(network: RipNetwork, seed: int, count: int) -> list[TrafficFlow]:
    generator = Random(seed * 15485863 + 11)
    names = sorted(network.routers)
    flows = []
    for _ in range(count):
        source, destination = generator.sample(names, 2)
        flows.append(TrafficFlow(source, destination, float(generator.randrange(20, 81, 5))))
    return flows


def run_traffic_trial(seed: int, *, routers: int = 12, edge_probability: float = 0.25, flow_count: int = 10) -> dict[str, Any]:
    """Deliver the same flows under hop-count RIP and under RIP-X traffic engineering."""
    rip = _traffic_network(seed, routers, edge_probability, {"profile": "rip"})
    rip.converge(max_rounds=500)
    flows = _random_flows(rip, seed, flow_count)
    offered = sum(flow.rate_mbps for flow in flows)
    rip_report = simulate_traffic(rip, flows)

    ripx = _traffic_network(seed, routers, edge_probability, {"profile": "ripx"})
    ripx.converge(max_rounds=500)
    engineered = engineer_traffic(ripx, flows, max_epochs=10, max_rounds=500)
    ripx_report = simulate_traffic(ripx, flows)

    def mean_hops(report) -> float:
        lengths = [len(path) - 1 for path in report.flow_paths.values() if path is not None]
        return statistics.fmean(lengths) if lengths else 0.0

    return {
        "seed": seed,
        "offered_mbps": offered,
        "rip": {
            "delivered_ratio": rip_report.delivered_mbps / offered,
            "maximum_utilization": rip_report.maximum_utilization,
            "mean_path_hops": mean_hops(rip_report),
        },
        "ripx": {
            "delivered_ratio": ripx_report.delivered_mbps / offered,
            "maximum_utilization": ripx_report.maximum_utilization,
            "mean_path_hops": mean_hops(ripx_report),
            "epochs": engineered.epochs,
            "epochs_run": len(engineered.epochs) - 1,
            "selected_epoch": engineered.selected_epoch,
            "te_control_messages": engineered.control_messages,
            "te_converged": engineered.converged,
        },
    }


def run_traffic_benchmark(
    seeds: list[int], *, routers: int = 12, edge_probability: float = 0.25, flow_count: int = 10
) -> dict[str, Any]:
    trials = [
        run_traffic_trial(seed, routers=routers, edge_probability=edge_probability, flow_count=flow_count)
        for seed in seeds
    ]
    by_config = {
        "rip": [trial["rip"] for trial in trials],
        "ripx": [trial["ripx"] for trial in trials],
    }
    metrics: dict[str, Callable[[dict[str, Any]], float | None]] = {
        "delivered_ratio": lambda run: run["delivered_ratio"],
        "maximum_utilization": lambda run: run["maximum_utilization"],
        "mean_path_hops": lambda run: run["mean_path_hops"],
    }
    summary = _summarize(by_config, metrics, "rip")
    summary["ripx"]["te_control_messages"] = describe_sample([float(run["te_control_messages"]) for run in by_config["ripx"]])
    summary["ripx"]["epochs_run"] = describe_sample([float(run["epochs_run"]) for run in by_config["ripx"]])
    summary["ripx"]["trials_improved"] = sum(
        1 for trial in trials if trial["ripx"]["delivered_ratio"] > trial["rip"]["delivered_ratio"] + 1e-9
    )
    summary["ripx"]["trials_worse"] = sum(
        1 for trial in trials if trial["ripx"]["delivered_ratio"] < trial["rip"]["delivered_ratio"] - 1e-9
    )
    return {
        "experiment": "traffic_engineering",
        "topology": {
            "type": "random",
            "routers": routers,
            "edge_probability": edge_probability,
            "bandwidth_mbps_choices": [50, 100, 200],
        },
        "flows_per_trial": flow_count,
        "seeds": seeds,
        "summary": summary,
        "trials": trials,
    }


def save_benchmark(result: dict[str, Any], destination: str | Path) -> None:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
