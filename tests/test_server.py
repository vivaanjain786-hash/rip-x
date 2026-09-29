import json
import threading
import urllib.error
import urllib.request

import pytest

from ripx.server import create_server


@pytest.fixture()
def api():
    server = create_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(path, body=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(base + path, data=data, method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    call.base = base
    yield call
    server.shutdown()
    server.server_close()


LINE = {"routers": ["R1", "R2", "R3"], "links": [["R1", "R2"], ["R2", "R3"]]}


def test_health_identifies_the_python_engine(api):
    assert api("/api/health") == (200, {"engine": "python", "name": "ripx"})


def test_static_visualizer_is_served(api):
    with urllib.request.urlopen(api.base + "/") as response:
        assert b"RIP-X" in response.read()
    with urllib.request.urlopen(api.base + "/app.js") as response:
        assert b"detectEngine" in response.read()


def test_state_requires_a_network(api):
    status, body = api("/api/state")
    assert status == 400 and "no network" in body["error"]


def test_network_converges_to_hop_counts_through_the_api(api):
    status, snapshot = api("/api/network", LINE)
    assert status == 200 and snapshot["round"] == 0
    status, result = api("/api/converge", {})
    routes = result["state"]["routers"]["R1"]["routes"]
    assert routes["R3"] == {"metric": 2, "nextHop": "R2", "reachable": True}
    assert result["state"]["converged"] is True


def test_step_reports_advertisements_for_animation(api):
    api("/api/network", LINE)
    status, result = api("/api/step", {"rounds": 1})
    assert status == 200
    assert sorted(map(tuple, result["advertisements"])) == [("R1", "R2"), ("R2", "R1"), ("R2", "R3"), ("R3", "R2")]
    assert result["state"]["controlMessages"] == 4


def test_failing_a_router_poisons_routes_and_recovery_relearns_them(api):
    api("/api/network", LINE)
    api("/api/converge", {})
    status, result = api("/api/router/toggle", {"router": "R3"})
    assert result["action"] == "failed" and result["state"]["routers"]["R3"]["up"] is False
    assert result["state"]["routers"]["R2"]["routes"]["R3"]["reachable"] is False
    api("/api/converge", {})
    status, result = api("/api/router/toggle", {"router": "R3"})
    assert result["action"] == "recovered"
    api("/api/converge", {})
    _, state = api("/api/state")
    assert state["routers"]["R1"]["routes"]["R3"]["reachable"] is True


def test_link_toggle_and_trace(api):
    api("/api/network", LINE)
    api("/api/converge", {})
    assert api("/api/trace", {"source": "R1", "destination": "R3"})[1] == {
        "outcome": "delivered",
        "path": ["R1", "R2", "R3"],
    }
    _, toggled = api("/api/link/toggle", {"u": "R2", "v": "R3"})
    assert toggled["action"] == "failed"
    _, trace = api("/api/trace", {"source": "R1", "destination": "R3"})
    assert trace["outcome"] == "blackhole"


def test_no_split_horizon_counts_to_infinity_through_the_api(api):
    api("/api/network", {**LINE, "config": {"split_horizon": False}})
    api("/api/converge", {})
    api("/api/router/toggle", {"router": "R3"})
    peak = 0
    for _ in range(40):
        _, result = api("/api/step", {"rounds": 1})
        route = result["state"]["routers"]["R1"]["routes"].get("R3")
        if route and route["reachable"]:
            peak = max(peak, route["metric"])
    assert peak >= 10


def test_ripx_profile_reports_adaptive_intervals_and_link_costs(api):
    _, snapshot = api("/api/network", {**LINE, "config": {"profile": "ripx"}})
    assert snapshot["config"]["updates"]["type"] == "adaptive"
    api("/api/converge", {})
    for _ in range(60):
        _, result = api("/api/step", {"rounds": 1})
    intervals = {name: router["updateInterval"] for name, router in result["state"]["routers"].items()}
    assert max(intervals.values()) > 5


def test_traffic_endpoint_measures_and_engineers(api):
    ladder = {
        "routers": ["A", "B", "C", "D", "E"],
        "links": [["A", "B"], ["B", "D"], ["A", "C"], ["C", "E"], ["E", "D"]],
        "config": {"profile": "ripx"},
    }
    api("/api/network", ladder)
    api("/api/converge", {})
    flows = [
        {"source": "A", "destination": "D", "rate_mbps": 90},
        {"source": "B", "destination": "D", "rate_mbps": 90},
    ]
    _, measured = api("/api/traffic", {"flows": flows})
    _, engineered = api("/api/traffic", {"flows": flows, "engineer": True})
    assert engineered["report"]["delivered_mbps"] > measured["report"]["delivered_mbps"]
    assert engineered["traffic_engineering"]["converged"] is True
    assert any(link["cost"] > 1 for link in engineered["state"]["links"])


def test_traffic_engineering_needs_the_congestion_metric(api):
    api("/api/network", LINE)
    status, body = api("/api/traffic", {"flows": [{"source": "R1", "destination": "R3", "rate_mbps": 10}], "engineer": True})
    assert status == 400 and "congestion_aware" in body["error"]


@pytest.mark.parametrize(
    "path, body",
    [
        ("/api/network", {"routers": [], "links": []}),
        ("/api/network", {"routers": ["R1"], "links": [["R1", "R9"]]}),
        ("/api/network", {"routers": ["R1", "R2"], "links": [["R1", "R2"]], "config": {"profile": "x"}}),
        ("/api/router/toggle", {"router": "R9"}),
        ("/api/step", {"rounds": 5000}),
        ("/api/link/toggle", {"u": "R1", "v": "R3"}),
        ("/api/trace", {"source": "R1", "destination": "zzz"}),
        ("/api/traffic", {"flows": []}),
    ],
)
def test_bad_requests_return_400_with_a_message(api, path, body):
    api("/api/network", LINE)
    status, payload = api(path, body)
    assert status == 400 and payload["error"]


def test_unknown_endpoint_is_404_and_bad_json_is_400(api):
    assert api("/api/nope", {})[0] == 404
    request = urllib.request.Request(api.base + "/api/step", data=b"{not json", method="POST")
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request)
    assert error.value.code == 400
