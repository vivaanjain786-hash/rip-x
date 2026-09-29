from ripx.routing.rip import INFINITY
from ripx.simulation.network import RipNetwork
from ripx.simulation.topologies import line


def _line(size: int, **config) -> RipNetwork:
    network = RipNetwork(**config)
    names = [f"R{index}" for index in range(1, size + 1)]
    for name in names:
        network.add_router(name)
    for left, right in zip(names, names[1:]):
        network.add_link(left, right)
    return network


def test_split_horizon_off_advertises_routes_back_to_learning_neighbor():
    network = _line(3, split_horizon=False)
    network.converge()
    assert network.routers["R3"].update_for("R2")["R1"] == 2


def test_split_horizon_without_poison_reverse_omits_routes():
    network = _line(3, poison_reverse=False)
    network.converge()
    assert "R1" not in network.routers["R3"].update_for("R2")


def test_poison_reverse_is_ignored_without_split_horizon():
    network = _line(3, split_horizon=False, poison_reverse=True)
    network.converge()
    assert network.routers["R3"].update_for("R2")["R1"] != INFINITY


def test_default_update_interval_matches_every_round_flooding():
    default = line(5).converge()
    explicit = _line(5, update_interval=1).converge()
    assert explicit == default


def test_update_interval_must_be_positive():
    try:
        RipNetwork(update_interval=0)
    except ValueError:
        return
    raise AssertionError("update_interval=0 should be rejected")


def test_stable_network_only_sends_on_periodic_rounds():
    network = _line(4, update_interval=5)
    network.converge()
    while not network.is_periodic_round():
        network.step()
    periodic = network.step()
    quiet = [network.step() for _ in range(4)]
    assert periodic.control_messages == 6
    assert all(result.control_messages == 0 for result in quiet)
    assert not any(result.changed for result in quiet)


def test_triggered_updates_propagate_between_periodic_rounds():
    network = _line(4, update_interval=30)
    network.converge()
    network.fail_link("R3", "R4")
    result = network.converge()
    assert not result.changed
    assert network.routers["R1"].route("R4").metric == INFINITY
    assert network.now % network.update_interval != 0


def test_without_triggered_updates_changes_wait_for_periodic_round():
    network = _line(4, update_interval=10, triggered_updates=False)
    network.converge()
    while not network.is_periodic_round():
        network.step()
    network.step()
    network.fail_link("R3", "R4")
    for _ in range(network.update_interval - 1):
        network.step()
    assert network.routers["R1"].route("R4").reachable
    network.converge()
    assert network.routers["R1"].route("R4").metric == INFINITY


def test_update_interval_must_be_shorter_than_route_timeout():
    try:
        RipNetwork(update_interval=180, route_timeout=180)
    except ValueError:
        return
    raise AssertionError("routes would time out between periodic updates")


def test_same_topology_sends_fewer_messages_with_longer_interval():
    every_round = _line(6)
    every_round.converge()
    periodic = _line(6, update_interval=10)
    periodic.converge()
    flood = sum(every_round.step().control_messages for _ in range(20))
    scheduled = sum(periodic.step().control_messages for _ in range(20))
    assert scheduled < flood
