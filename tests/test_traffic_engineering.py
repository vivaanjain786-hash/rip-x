import pytest

from ripx.analytics.experiment import run_scenario, validate_against_bellman_ford
from ripx.routing.metrics import CongestionAwareCost
from ripx.simulation.network import RipNetwork
from ripx.simulation.traffic import TrafficFlow, simulate_traffic
from ripx.simulation.traffic_engineering import engineer_traffic


def _ladder() -> RipNetwork:
    """A-B-D is the short path; A-C-E-D is a longer detour with the same capacity."""
    network = RipNetwork(cost_policy=CongestionAwareCost(), route_timeout=60)
    for name in ("A", "B", "C", "D", "E"):
        network.add_router(name)
    for left, right in (("A", "B"), ("B", "D"), ("A", "C"), ("C", "E"), ("E", "D")):
        network.add_link(left, right, bandwidth_mbps=100.0)
    return network


def test_traffic_engineering_moves_flow_off_an_oversubscribed_path():
    network = _ladder()
    network.converge()
    flows = [TrafficFlow("A", "D", 90.0), TrafficFlow("B", "D", 90.0)]
    before = simulate_traffic(network, flows)
    assert before.maximum_utilization == pytest.approx(1.8)

    result = engineer_traffic(network, flows)

    assert result.final.delivered_mbps > before.delivered_mbps
    assert result.final.maximum_utilization < before.maximum_utilization
    assert result.final.flow_paths["flow-1:A->D"] == ["A", "C", "E", "D"]
    assert result.converged
    assert validate_against_bellman_ford(network)["valid"]


def test_flows_between_the_same_pair_cannot_be_split_by_single_path_rip():
    """RIP installs one next hop per destination, so identical flows move together."""
    network = _ladder()
    network.converge()
    flows = [TrafficFlow("A", "D", 90.0), TrafficFlow("A", "D", 90.0)]
    before = simulate_traffic(network, flows)
    result = engineer_traffic(network, flows)
    assert result.final.delivered_mbps >= before.delivered_mbps - 1e-9
    paths = list(result.final.flow_paths.values())
    assert paths[0] == paths[1]


def test_traffic_engineering_never_delivers_less_than_plain_rip():
    network = _ladder()
    network.converge()
    flows = [TrafficFlow("A", "D", 30.0)]
    baseline = simulate_traffic(network, flows).delivered_mbps
    result = engineer_traffic(network, flows)
    assert result.final.delivered_mbps >= baseline - 1e-9
    assert result.selected_epoch == 0  # nothing was congested, so costs stay at one hop


def test_traffic_engineering_requires_congestion_aware_metric():
    network = RipNetwork()
    network.add_router("A")
    with pytest.raises(ValueError):
        engineer_traffic(network, [])


def test_traffic_engineering_epochs_are_bounded():
    network = _ladder()
    network.converge()
    result = engineer_traffic(network, [TrafficFlow("A", "D", 500.0)], max_epochs=2)
    assert len(result.epochs) <= 3


def test_engineered_scenario_reports_before_and_after(tmp_path):
    scenario = tmp_path / "te.json"
    scenario.write_text(
        """{
          "name": "te", "topology": "ring", "routers": 6,
          "rip": {"profile": "ripx"},
          "traffic_engineering": {"max_epochs": 6},
          "flows": [
            {"source": "R1", "destination": "R3", "rate_mbps": 70},
            {"source": "R2", "destination": "R3", "rate_mbps": 60},
            {"source": "R1", "destination": "R4", "rate_mbps": 40}
          ]
        }""",
        encoding="utf-8",
    )
    result = run_scenario(scenario)
    assert result["rip"]["profile"] == "ripx"
    phase = result["phases"][0]
    engineering = phase["traffic_engineering"]
    assert engineering["delivered_mbps_after"] > engineering["delivered_mbps_before"]
    assert phase["traffic"]["delivered_mbps"] == pytest.approx(engineering["delivered_mbps_after"])
    assert all("cost" in link for link in phase["telemetry"]["links"])


def test_bundled_traffic_engineering_scenario_runs():
    result = run_scenario("scenarios/ripx-traffic-engineering-ring.json")
    assert [phase["event"] for phase in result["phases"]] == ["baseline", "link_failure", "link_recovery"]
    for phase in result["phases"]:
        engineering = phase["traffic_engineering"]
        assert engineering["delivered_mbps_after"] >= engineering["delivered_mbps_before"] - 1e-9
        assert engineering["converged"]
