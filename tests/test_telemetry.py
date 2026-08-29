from ripx.analytics.telemetry import collect_telemetry
from ripx.simulation.topologies import ring
from ripx.simulation.traffic import TrafficFlow, simulate_traffic


def test_telemetry_reports_routes_links_and_traffic_utilization():
    network = ring(4)
    network.converge()
    traffic = simulate_traffic(network, [TrafficFlow("R1", "R3", 20.0)])
    telemetry = collect_telemetry(network, traffic)
    assert telemetry["active_routers"] == 4
    assert telemetry["reachable_routes"] == 12
    assert telemetry["route_changes_total"] > 0
    assert any(link["utilization"] == 0.2 for link in telemetry["links"])


def test_telemetry_marks_router_adjacent_links_down():
    network = ring(4)
    network.converge()
    network.fail_router("R2")
    telemetry = collect_telemetry(network)
    assert telemetry["failed_routers"] == ["R2"]
    assert next(link for link in telemetry["links"] if link["link"] == "R1-R2")["up"] is False
