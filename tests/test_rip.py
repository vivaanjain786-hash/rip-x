from ripx.routing.rip import INFINITY, RipRouter
from ripx.simulation.topologies import line, ring


def test_line_converges_to_hop_count_routes():
    network = line(4)
    result = network.converge()
    assert result.rounds <= 4
    assert network.routers["R1"].route("R4").metric == 3
    assert network.routers["R4"].route("R1").metric == 3


def test_poison_reverse_advertises_infinity_back_to_learning_neighbor():
    network = line(3)
    network.converge()
    assert network.routers["R3"].update_for("R2")["R1"] == INFINITY


def test_ring_recovers_with_alternate_path_after_link_failure():
    network = ring(4)
    network.converge()
    network.fail_link("R1", "R2")
    network.converge()
    route = network.routers["R1"].route("R2")
    assert route is not None
    assert route.metric == 3
    assert route.next_hop == "R4"


def test_failed_route_is_garbage_collected():
    network = line(2)
    router = network.routers["R1"]
    router.garbage_collection = 2
    network.converge()
    network.fail_link("R1", "R2")
    network.step()
    assert router.route("R2").metric == INFINITY
    network.step()
    assert router.route("R2") is None


def test_timeout_invalidates_silent_learned_route_then_collects_it():
    router = RipRouter("R1", route_timeout=1, garbage_collection=1)
    router.receive("R2", {"R3": 1}, now=0)
    router.age_routes(now=1)
    assert router.route("R3").metric == INFINITY
    router.age_routes(now=2)
    assert router.route("R3") is None
