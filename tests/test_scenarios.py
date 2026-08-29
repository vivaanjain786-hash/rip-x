import json

import pytest

from ripx.analytics.experiment import run_scenario
from ripx.simulation.scenarios import load_scenario


def test_loads_and_runs_a_file_backed_scenario(tmp_path):
    source = tmp_path / "scenario.json"
    source.write_text(json.dumps({"name": "small-ring", "topology": "ring", "routers": 4}))
    scenario = load_scenario(source)
    result = run_scenario(source)
    assert scenario.name == "small-ring"
    assert result["scenario"] == "small-ring"
    assert result["routers"] == 4
    assert result["convergence_rounds"] <= 4


def test_rejects_unknown_topology(tmp_path):
    source = tmp_path / "scenario.json"
    source.write_text(json.dumps({"name": "bad", "topology": "mesh", "routers": 4}))
    with pytest.raises(ValueError, match="baseline topology"):
        load_scenario(source)


def test_seeded_random_scenario_is_reproducible(tmp_path):
    source = tmp_path / "random.json"
    source.write_text(
        json.dumps({"name": "seeded", "topology": "random", "routers": 12, "seed": 42, "edge_probability": 0.2})
    )
    assert run_scenario(source) == run_scenario(source)


def test_failure_scenario_measures_each_reconvergence(tmp_path):
    source = tmp_path / "failure.json"
    source.write_text(
        json.dumps(
            {
                "name": "failure-test",
                "topology": "ring",
                "routers": 5,
                "events": [
                    {"type": "router_failure", "router": "R2"},
                    {"type": "router_recovery", "router": "R2"},
                ],
            }
        )
    )
    result = run_scenario(source)
    assert [phase["event"] for phase in result["phases"]] == [
        "baseline",
        "router_failure",
        "router_recovery",
    ]


def test_congestion_scenario_reports_measured_bottleneck(tmp_path):
    source = tmp_path / "congestion.json"
    source.write_text(
        json.dumps(
            {
                "name": "congestion",
                "topology": "line",
                "routers": 3,
                "flows": [{"source": "R1", "destination": "R3", "rate_mbps": 150}],
            }
        )
    )
    result = run_scenario(source)
    traffic = result["phases"][0]["traffic"]
    assert traffic["maximum_utilization"] == 1.5
    assert traffic["dropped_mbps"] > 0


def test_impairment_scenario_reports_loss_then_restoration(tmp_path):
    source = tmp_path / "impairment.json"
    source.write_text(
        json.dumps(
            {
                "name": "impairment",
                "topology": "ring",
                "routers": 4,
                "flows": [{"source": "R1", "destination": "R3", "rate_mbps": 20}],
                "events": [
                    {"type": "packet_loss_spike", "link": ["R1", "R2"], "packet_loss": 0.25},
                    {"type": "link_restore", "link": ["R1", "R2"]},
                ],
            }
        )
    )
    phases = run_scenario(source)["phases"]
    assert phases[1]["traffic"]["delivered_mbps"] == 15.0
    assert phases[2]["traffic"]["delivered_mbps"] == 20.0
