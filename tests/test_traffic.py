from ripx.simulation.topologies import ring
from ripx.simulation.traffic import TrafficFlow, simulate_traffic


def test_traffic_uses_current_rip_path_and_reports_utilization():
    network = ring(5)
    network.converge()
    report = simulate_traffic(network, [TrafficFlow("R1", "R3", 20.0)])
    assert report.flow_paths["flow-1:R1->R3"] == ["R1", "R2", "R3"]
    assert report.link_utilization["R1-R2"] == 0.2
    assert report.delivered_mbps == 20.0


def test_traffic_becomes_unroutable_when_destination_router_fails():
    network = ring(5)
    network.converge()
    network.fail_router("R3")
    network.converge()
    report = simulate_traffic(network, [TrafficFlow("R1", "R3", 20.0)])
    assert report.flow_paths["flow-1:R1->R3"] is None
    assert report.unroutable_mbps == 20.0
