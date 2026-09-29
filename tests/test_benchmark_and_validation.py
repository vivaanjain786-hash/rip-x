import json

import pytest

from ripx.analytics.benchmark import (
    Timeline,
    choose_failures,
    describe_sample,
    run_traffic_benchmark,
    run_update_benchmark,
    run_update_trial,
    UPDATE_CONFIGURATIONS,
)
from ripx.analytics.validation import expected_metrics, routing_state, trace_next_hops
from ripx.benchmark import main as benchmark_main
from ripx.benchmark import render_report
from ripx.simulation.topologies import line, random_connected, ring

SHORT = Timeline(link_failure=40, link_recovery=80, router_failure=120, router_recovery=160, horizon=200)


def test_expected_metrics_match_converged_rip_tables():
    network = ring(6)
    network.converge()
    state = routing_state(network, expected_metrics(network))
    assert state == {"pairs": 30, "incorrect": 0, "blackhole": 0, "loop": 0, "stale": 0}


def test_routing_state_flags_a_failed_link_before_reconvergence():
    network = line(4)
    network.converge()
    network.fail_link("R2", "R3")
    state = routing_state(network, expected_metrics(network))
    assert state["stale"] > 0 or state["incorrect"] > 0


def test_trace_next_hops_detects_a_forced_loop():
    network = line(3)
    network.converge()
    route = network.routers["R1"].routes["R3"]
    network.routers["R2"].routes["R3"] = type(route)("R3", 2, "R1", "R1", 0)
    assert trace_next_hops(network, "R1", "R3") == "loop"


def test_describe_sample_confidence_interval():
    stats = describe_sample([1.0, 2.0, 3.0, 4.0, 5.0])
    assert stats["mean"] == 3.0
    assert stats["ci95_low"] < 3.0 < stats["ci95_high"]
    assert describe_sample([7.0]) == {"n": 1, "mean": 7.0, "stdev": 0.0, "ci95_low": 7.0, "ci95_high": 7.0}


def test_failure_choice_is_deterministic_and_keeps_network_connected():
    network = random_connected(15, seed=4, edge_probability=0.2)
    first = choose_failures(network, 4)
    assert first == choose_failures(network, 4)
    link, router = first
    assert router in network.routers and frozenset(link) in network.links


def test_update_trial_is_reproducible():
    config = UPDATE_CONFIGURATIONS["ripx"]
    first = run_update_trial(config, seed=3, routers=12, timeline=SHORT)
    second = run_update_trial(config, seed=3, routers=12, timeline=SHORT)
    assert first == second


def test_adaptive_updates_cut_control_messages_and_every_event_converges():
    result = run_update_benchmark([0, 1, 2], routers=12, timeline=SHORT)
    rip, ripx = result["summary"]["rip"], result["summary"]["ripx"]
    assert ripx["control_messages"]["mean"] < rip["control_messages"]["mean"]
    assert ripx["control_messages"]["paired_difference_vs_rip"]["ci95_high"] < 0
    for name, metrics in result["summary"].items():
        for key, stats in metrics.items():
            assert stats["unconverged_trials"] == 0, (name, key)
    # Same seeds see the same failures in every configuration.
    failures = {tuple((t["failed_link"], t["failed_router"]) for t in trials) for trials in result["trials"].values()}
    assert len(failures) == 1


def test_traffic_benchmark_never_reports_worse_delivery_than_measured():
    result = run_traffic_benchmark([0, 1, 2], routers=10)
    summary = result["summary"]["ripx"]
    assert summary["trials_worse"] == 0
    assert summary["delivered_ratio"]["mean"] >= result["summary"]["rip"]["delivered_ratio"]["mean"]
    for trial in result["trials"]:
        assert trial["ripx"]["te_converged"]


def test_benchmark_cli_writes_json_report_and_plot(tmp_path):
    benchmark_main(["--seeds", "2", "--routers", "10", "--output", str(tmp_path)])
    for name in ("update_control.json", "traffic_engineering.json", "report.md", "benchmark.png"):
        assert (tmp_path / name).stat().st_size > 0
    updates = json.loads((tmp_path / "update_control.json").read_text())
    assert updates["seeds"] == [0, 1]
    report = (tmp_path / "report.md").read_text()
    assert "## 1. Update control" in report and "## Caveats" in report


def test_report_mentions_every_configuration():
    updates = run_update_benchmark([0, 1], routers=10, timeline=SHORT)
    traffic = run_traffic_benchmark([0, 1], routers=10)
    report = render_report(updates, traffic)
    for name in updates["configurations"]:
        assert f"`{name}`" in report
