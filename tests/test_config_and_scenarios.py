import json

import pytest

from ripx.analytics.experiment import run_scenario
from ripx.config import PROFILES, network_options, resolve_config
from ripx.routing.metrics import CongestionAwareCost, HopCountCost
from ripx.routing.scheduling import AdaptiveUpdateSchedule, FixedUpdateSchedule
from ripx.simulation.scenarios import load_scenario
from ripx.simulation.topologies import line, ring


def test_default_config_is_the_original_baseline():
    options = network_options(None)
    assert isinstance(options["schedule"], FixedUpdateSchedule) and options["schedule"].interval == 1
    assert isinstance(options["cost_policy"], HopCountCost)


def test_ripx_profile_enables_adaptive_updates_requests_and_congestion_metric():
    options = network_options({"profile": "ripx"})
    assert isinstance(options["schedule"], AdaptiveUpdateSchedule)
    assert isinstance(options["cost_policy"], CongestionAwareCost)
    assert options["request_on_loss"] is True


def test_explicit_settings_override_profile_and_schedules_are_not_shared():
    config = {"profile": "ripx", "request_on_loss": False}
    first, second = network_options(config), network_options(config)
    assert first["request_on_loss"] is False
    assert first["schedule"] is not second["schedule"]


@pytest.mark.parametrize(
    "config",
    [{"profile": "mystery"}, {"bogus": 1}, {"split_horizon": "yes"}, {"route_timeout": 0}, {"updates": []}],
)
def test_invalid_config_is_rejected(config):
    with pytest.raises(ValueError):
        resolve_config(config)


def test_topology_factories_pass_options_to_the_network():
    network = ring(5, split_horizon=False, triggered_updates=False)
    assert network.split_horizon is False and network.triggered_updates is False
    assert line(3, **network_options({"profile": "rip"})).update_interval == 5


def test_profiles_compared_in_benchmark_share_timers():
    assert PROFILES["rip"]["route_timeout"] == PROFILES["ripx"]["route_timeout"]


def _write(tmp_path, body):
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def test_scenario_links_set_capacity(tmp_path):
    path = _write(
        tmp_path,
        {
            "name": "caps", "topology": "line", "routers": 3,
            "links": [{"link": ["R1", "R2"], "bandwidth_mbps": 10}],
            "flows": [{"source": "R1", "destination": "R3", "rate_mbps": 20}],
        },
    )
    result = run_scenario(path)
    assert result["phases"][0]["traffic"]["maximum_utilization"] == pytest.approx(2.0)


@pytest.mark.parametrize(
    "extra",
    [
        {"links": [{"link": ["R1"]}]},
        {"links": [{"link": ["R1", "R2"], "bandwidth_mbps": 0}]},
        {"links": [{"link": ["R1", "R2"], "packet_loss": 2}]},
        {"rip": {"profile": "mystery"}},
        {"rip": "ripx"},
        {"traffic_engineering": 3},
    ],
)
def test_invalid_new_scenario_fields_are_rejected(tmp_path, extra):
    path = _write(tmp_path, {"name": "bad", "topology": "line", "routers": 3, **extra})
    with pytest.raises(ValueError):
        load_scenario(path)


def test_rip_profiles_all_converge_to_the_same_hop_count_routes(tmp_path):
    metrics = {}
    for profile in ("baseline", "rip", "ripx"):
        path = _write(tmp_path, {"name": profile, "topology": "ring", "routers": 8, "rip": {"profile": profile}})
        result = run_scenario(path)
        metrics[profile] = result["phases"][0]["telemetry"]["average_reachable_hops"]
    assert len(set(metrics.values())) == 1


def test_all_bundled_scenarios_load_and_run():
    import glob

    for path in sorted(glob.glob("scenarios/*.json")):
        assert run_scenario(path)["scenario"]
