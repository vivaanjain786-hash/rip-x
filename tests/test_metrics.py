import pytest

from ripx.analytics.experiment import validate_against_bellman_ford
from ripx.routing.metrics import CongestionAwareCost, HopCountCost, cost_policy_from_config
from ripx.simulation.network import RipNetwork


def _cost(policy=None, **kwargs):
    policy = policy or CongestionAwareCost()
    return policy.cost(**{"utilization": 0.0, "latency_ms": 1.0, "packet_loss": 0.0, **kwargs})


def test_hop_count_cost_is_always_one():
    assert HopCountCost().cost(utilization=5.0, latency_ms=999, packet_loss=1.0) == 1


def test_idle_link_costs_one_hop():
    assert _cost() == 1


def test_cost_rises_with_utilization_thresholds_and_is_capped():
    assert _cost(utilization=0.85) == 2
    assert _cost(utilization=1.2) == 3
    assert _cost(utilization=1.2, latency_ms=200, packet_loss=0.5) == 3


def test_latency_and_loss_each_add_one():
    assert _cost(latency_ms=80) == 2
    assert _cost(packet_loss=0.1) == 2
    assert _cost(latency_ms=80, packet_loss=0.1) == 3


def test_hysteresis_keeps_cost_until_load_clearly_drops():
    policy = CongestionAwareCost()
    assert _cost(policy, utilization=0.75, previous=2) == 2
    assert _cost(policy, utilization=0.65, previous=2) == 1
    assert _cost(policy, utilization=0.75, previous=1) == 1


def test_invalid_policies_are_rejected():
    with pytest.raises(ValueError):
        CongestionAwareCost(max_cost=0)
    with pytest.raises(ValueError):
        CongestionAwareCost(utilization_thresholds=(1.0, 0.5))
    with pytest.raises(ValueError):
        cost_policy_from_config({"type": "mystery"})


def test_policy_from_config_reads_overrides():
    policy = cost_policy_from_config({"type": "congestion_aware", "max_cost": 2, "loss_threshold": 0.5})
    assert policy.max_cost == 2 and policy.loss_threshold == 0.5


def _square(**options) -> RipNetwork:
    network = RipNetwork(**options)
    for name in ("A", "B", "C", "D"):
        network.add_router(name)
    for left, right in (("A", "B"), ("B", "D"), ("A", "C"), ("C", "D")):
        network.add_link(left, right)
    return network


def test_link_cost_changes_the_chosen_path_and_metric():
    network = _square(cost_policy=CongestionAwareCost())
    network.converge()
    assert network.routers["A"].route("D").metric == 2
    network.set_link_costs({frozenset(("A", "B")): 3})
    network.converge()
    route = network.routers["A"].route("D")
    assert route.next_hop == "C" and route.metric == 2


def test_latency_spike_raises_cost_and_restore_lowers_it():
    network = _square(cost_policy=CongestionAwareCost())
    network.converge()
    network.set_link_conditions("A", "B", latency_ms=120)
    assert network.link_cost("A", "B") == 2
    network.restore_link_conditions("A", "B")
    assert network.link_cost("A", "B") == 1


def test_costs_match_bellman_ford_after_convergence():
    network = _square(cost_policy=CongestionAwareCost())
    network.converge()
    network.set_link_costs({frozenset(("A", "B")): 3, frozenset(("C", "D")): 2})
    network.converge()
    assert validate_against_bellman_ford(network)["valid"]


def test_set_link_costs_validates_input():
    network = _square()
    with pytest.raises(ValueError):
        network.set_link_costs({frozenset(("A", "D")): 2})
    with pytest.raises(ValueError):
        network.set_link_costs({frozenset(("A", "B")): 0})
