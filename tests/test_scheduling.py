import pytest

from ripx.routing.scheduling import AdaptiveUpdateSchedule, FixedUpdateSchedule, schedule_from_config
from ripx.simulation.network import RipNetwork


def _ring(size: int, **options) -> RipNetwork:
    network = RipNetwork(**options)
    names = [f"R{index}" for index in range(1, size + 1)]
    for name in names:
        network.add_router(name)
    for index, name in enumerate(names):
        network.add_link(name, names[(index + 1) % size])
    return network


def test_fixed_schedule_is_due_on_multiples_of_interval():
    schedule = FixedUpdateSchedule(5)
    assert [now for now in range(11) if schedule.is_due("R1", now)] == [0, 5, 10]


def test_adaptive_interval_grows_only_while_stable_and_is_capped():
    schedule = AdaptiveUpdateSchedule(min_interval=5, max_interval=20, growth=2)
    schedule.register("R1")
    for expected in (10, 20, 20):
        schedule.record_periodic("R1", now=0, stable=True)
        assert schedule.current_interval("R1") == expected
    schedule.record_periodic("R1", now=0, stable=False)
    assert schedule.current_interval("R1") == 20


def test_adaptive_change_resets_interval_and_pulls_next_update_forward():
    schedule = AdaptiveUpdateSchedule(min_interval=5, max_interval=40)
    schedule.register("R1")
    schedule.record_periodic("R1", now=0, stable=True)
    schedule.record_periodic("R1", now=10, stable=True)
    assert schedule.next_due["R1"] == 30
    schedule.record_change("R1", now=12)
    assert schedule.current_interval("R1") == 5
    assert schedule.next_due["R1"] == 17


@pytest.mark.parametrize(
    "kwargs",
    [{"min_interval": 0}, {"min_interval": 10, "max_interval": 5}, {"growth": 0}],
)
def test_adaptive_schedule_rejects_bad_parameters(kwargs):
    with pytest.raises(ValueError):
        AdaptiveUpdateSchedule(**kwargs)


def test_schedule_from_config():
    assert isinstance(schedule_from_config(None), FixedUpdateSchedule)
    assert schedule_from_config({"type": "fixed", "interval": 7}).interval == 7
    adaptive = schedule_from_config({"type": "adaptive", "min_interval": 3, "max_interval": 9})
    assert (adaptive.min_interval, adaptive.max_interval) == (3, 9)
    with pytest.raises(ValueError):
        schedule_from_config({"type": "mystery"})


def test_adaptive_network_sends_far_fewer_messages_when_stable():
    fixed = _ring(10, schedule=FixedUpdateSchedule(5), route_timeout=180)
    adaptive = _ring(10, schedule=AdaptiveUpdateSchedule(5, 40), route_timeout=180)
    totals = []
    for network in (fixed, adaptive):
        network.converge()
        totals.append(sum(network.step().control_messages for _ in range(300)))
    assert totals[1] < totals[0] / 3


def test_route_requests_repair_a_failed_link_faster_than_waiting_for_periodic_updates():
    times = {}
    for name, requests in (("without", False), ("with", True)):
        network = _ring(10, schedule=AdaptiveUpdateSchedule(5, 40), request_on_loss=requests)
        network.converge()
        for _ in range(300):
            network.step()
        network.fail_link("R1", "R2")
        rounds = 0
        while not network.routers["R1"].route("R2").reachable:
            network.step()
            rounds += 1
            assert rounds < 100
        times[name] = rounds
        assert network.routers["R1"].route("R2").metric == 9
    assert times["with"] < times["without"]


def test_network_rejects_interval_not_shorter_than_timeout():
    with pytest.raises(ValueError):
        RipNetwork(schedule=AdaptiveUpdateSchedule(5, 200), route_timeout=180)


def test_recovered_router_restarts_with_only_itself():
    network = _ring(4)
    network.converge()
    network.fail_router("R2")
    network.converge()
    network.recover_router("R2")
    assert set(network.routers["R2"].routes) == {"R2"}
    network.converge()
    assert network.routers["R2"].route("R4").metric == 2
