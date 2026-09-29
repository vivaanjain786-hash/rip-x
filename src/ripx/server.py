"""HTTP server that drives the browser visualizer with the Python RIP engine.

    python -m ripx.server            # http://localhost:8080

The browser keeps only layout and animation. Every routing decision, failure,
trace and traffic measurement comes from ``RipNetwork`` through a small JSON
API, so the visualizer and the experiments share one source of truth.
"""

from __future__ import annotations

import argparse
import json
import threading
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ripx.analytics.benchmark import UPDATE_CONFIGURATIONS, Timeline, run_traffic_trial, run_update_trial
from ripx.analytics.validation import trace_next_hops
from ripx.config import describe_options, network_options, resolve_config
from ripx.routing.rip import INFINITY
from ripx.simulation.network import RipNetwork
from ripx.simulation.traffic import TrafficFlow, simulate_traffic
from ripx.simulation.traffic_engineering import engineer_traffic

VISUALIZER_DIR = Path(__file__).resolve().parents[2] / "visualizer"
RESULTS_DIR = Path(__file__).resolve().parents[2] / "results" / "benchmark"
MAX_ROUTERS = 200
DEMO_TIMELINE = Timeline(link_failure=60, link_recovery=120, router_failure=180, router_recovery=240, horizon=300)


class BenchmarkJob:
    """A background benchmark run started from the dashboard (one at a time)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.state = "idle"
        self.seeds = 0
        self.error = ""

    def start(self, seeds: int) -> bool:
        from ripx.benchmark import run_and_save

        with self.lock:
            if self.state == "running":
                return False
            self.state, self.seeds, self.error = "running", seeds, ""

        def work() -> None:
            try:
                run_and_save(list(range(seeds)), RESULTS_DIR / "live", plot=False)
                outcome = ("done", "")
            except Exception as error:  # reported to the page, not raised in the thread
                outcome = ("error", str(error))
            with self.lock:
                self.state, self.error = outcome

        threading.Thread(target=work, daemon=True).start()
        return True

    def status(self) -> dict[str, Any]:
        with self.lock:
            return {"state": self.state, "seeds": self.seeds, "error": self.error}


BENCHMARK_JOB = BenchmarkJob()


def latest_benchmark() -> dict[str, Any]:
    """Summary of the newest benchmark on disk (a dashboard run, else the committed one)."""
    for folder, source in ((RESULTS_DIR / "live", "dashboard run"), (RESULTS_DIR, "committed run")):
        try:
            updates = json.loads((folder / "update_control.json").read_text(encoding="utf-8"))
            traffic = json.loads((folder / "traffic_engineering.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        return {
            "source": source,
            "seeds": len(updates["seeds"]),
            "update_control": updates["summary"],
            "traffic_engineering": traffic["summary"],
        }
    return {"source": None}


def compare(payload: dict[str, Any]) -> dict[str, Any]:
    """Run standard RIP and RIP-X on the same topology and failures; return per-round series."""
    routers, seed = int(payload.get("routers", 16)), int(payload.get("seed", 0))
    if not 6 <= routers <= 40:
        raise ApiError("routers must be between 6 and 40")
    try:
        runs = {
            name: run_update_trial(UPDATE_CONFIGURATIONS[name], seed=seed, routers=routers, timeline=DEMO_TIMELINE, series=True)
            for name in ("rip", "ripx")
        }
    except (ValueError, RuntimeError) as error:
        raise ApiError(str(error)) from error
    return {"timeline": DEMO_TIMELINE.__dict__, "events": dict(DEMO_TIMELINE.events()), "runs": runs}


def traffic_demo(payload: dict[str, Any]) -> dict[str, Any]:
    return run_traffic_trial(int(payload.get("seed", 0)), routers=12)


class ApiError(ValueError):
    """A request the engine cannot apply; reported to the browser as HTTP 400."""


class EngineSession:
    """One live network shared by the browser tabs talking to this server."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.network: RipNetwork | None = None
        self.config: dict[str, Any] = {}
        self.options: dict[str, Any] = {}
        self.control_messages = 0
        self.converged = False

    # -- lifecycle -------------------------------------------------------
    def build(self, payload: dict[str, Any]) -> dict[str, Any]:
        routers = payload.get("routers")
        links = payload.get("links")
        if not isinstance(routers, list) or not routers or not all(isinstance(name, str) and name for name in routers):
            raise ApiError("routers must be a non-empty list of names")
        if len(routers) > MAX_ROUTERS:
            raise ApiError(f"at most {MAX_ROUTERS} routers are supported")
        if not isinstance(links, list):
            raise ApiError("links must be a list of [router, router] pairs")
        config = payload.get("config") or {}
        if not isinstance(config, dict):
            raise ApiError("config must be an object")
        try:
            resolve_config(config)
            options = network_options(config)
            network = RipNetwork(**options)
            for name in routers:
                network.add_router(name)
            for link in links:
                if not isinstance(link, list) or len(link) != 2:
                    raise ApiError("each link must be a [router, router] pair")
                network.add_link(str(link[0]), str(link[1]))
        except ValueError as error:
            raise ApiError(str(error)) from error
        self.network = network
        self.config = config
        self.options = options
        self.control_messages = 0
        self.converged = False
        return self.snapshot()

    def require(self) -> RipNetwork:
        if self.network is None:
            raise ApiError("no network loaded; POST /api/network first")
        return self.network

    # -- actions ---------------------------------------------------------
    def step(self, rounds: int) -> dict[str, Any]:
        network = self.require()
        if not 1 <= rounds <= 1000:
            raise ApiError("rounds must be between 1 and 1000")
        advertisements: list[tuple[str, str]] = []
        requests: list[tuple[str, str]] = []
        changed = False
        for _ in range(rounds):
            result = network.step()
            self.control_messages += result.control_messages
            advertisements = network.last_messages
            requests = network.last_requests
            changed = result.changed
        self.converged = not changed and not network.has_pending_updates()
        return {
            "changed": changed,
            "advertisements": [list(pair) for pair in advertisements],
            "requests": [list(pair) for pair in requests],
            "state": self.snapshot(),
        }

    def converge(self, max_rounds: int) -> dict[str, Any]:
        network = self.require()
        result = network.converge(max_rounds)
        self.control_messages += result.control_messages
        self.converged = not result.changed
        return {"rounds": result.rounds, "control_messages": result.control_messages, "state": self.snapshot()}

    def toggle_router(self, router: str) -> dict[str, Any]:
        network = self.require()
        if router not in network.routers:
            raise ApiError(f"unknown router {router!r}")
        if router in network.failed_routers:
            network.recover_router(router)
            action = "recovered"
        else:
            network.fail_router(router)
            action = "failed"
        self.converged = False
        return {"action": action, "state": self.snapshot()}

    def toggle_link(self, left: str, right: str) -> dict[str, Any]:
        network = self.require()
        key = frozenset((left, right))
        if key not in network.links:
            raise ApiError(f"unknown link {left}-{right}")
        if network.links[key].up:
            network.fail_link(left, right)
            action = "failed"
        else:
            network.recover_link(left, right)
            action = "recovered"
        self.converged = False
        return {"action": action, "state": self.snapshot()}

    def set_link(self, payload: dict[str, Any]) -> dict[str, Any]:
        network = self.require()
        link = payload.get("link")
        if not isinstance(link, list) or len(link) != 2:
            raise ApiError("link must be a [router, router] pair")
        properties = {
            key: float(payload[key]) for key in ("bandwidth_mbps", "latency_ms", "packet_loss") if key in payload
        }
        try:
            network.set_link_conditions(str(link[0]), str(link[1]), **properties)
        except (KeyError, ValueError) as error:
            raise ApiError(str(error)) from error
        self.converged = False
        return {"state": self.snapshot()}

    def trace(self, source: str, destination: str) -> dict[str, Any]:
        network = self.require()
        if source not in network.routers or destination not in network.routers:
            raise ApiError("source and destination must be existing routers")
        if source in network.failed_routers or destination in network.failed_routers:
            return {"outcome": "blackhole", "path": [source]}
        path = [source]
        current = source
        outcome = trace_next_hops(network, source, destination)
        seen = {source}
        while current != destination:
            route = network.routers[current].route(destination)
            if route is None or not route.reachable or route.next_hop is None:
                break
            current = route.next_hop
            path.append(current)
            if current in seen:
                break
            seen.add(current)
        return {"outcome": outcome, "path": path}

    def traffic(self, payload: dict[str, Any]) -> dict[str, Any]:
        network = self.require()
        flows_data = payload.get("flows")
        if not isinstance(flows_data, list) or not flows_data:
            raise ApiError("flows must be a non-empty list")
        try:
            flows = [
                TrafficFlow(str(flow["source"]), str(flow["destination"]), float(flow["rate_mbps"]))
                for flow in flows_data
            ]
        except (KeyError, TypeError, ValueError) as error:
            raise ApiError("each flow needs source, destination and rate_mbps") from error
        response: dict[str, Any] = {}
        try:
            if payload.get("engineer"):
                engineered = engineer_traffic(network, flows)
                self.control_messages += engineered.control_messages
                response["traffic_engineering"] = engineered.summary()
            else:
                network.record_utilization(_utilization_keys(network, simulate_traffic(network, flows)))
            report = simulate_traffic(network, flows)
        except ValueError as error:
            raise ApiError(str(error)) from error
        response["report"] = {
            "delivered_mbps": report.delivered_mbps,
            "dropped_mbps": report.dropped_mbps,
            "unroutable_mbps": report.unroutable_mbps,
            "maximum_utilization": report.maximum_utilization,
            "bottleneck_links": report.bottleneck_links,
            "flow_paths": report.flow_paths,
            "link_utilization": report.link_utilization,
        }
        response["state"] = self.snapshot()
        return response

    # -- state -----------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        network = self.require()
        routers: dict[str, Any] = {}
        for name, router in network.routers.items():
            routes = {
                destination: {
                    "metric": route.metric,
                    "nextHop": route.next_hop if route.next_hop is not None else name,
                    "reachable": route.metric < INFINITY,
                }
                for destination, route in router.routes.items()
            }
            routers[name] = {
                "up": name not in network.failed_routers,
                "updateInterval": network.schedule.current_interval(name),
                "routes": routes,
            }
        links = []
        for key, link in network.links.items():
            links.append(
                {
                    "u": link.left,
                    "v": link.right,
                    "up": link.up,
                    "cost": network.link_costs[key],
                    "bandwidth_mbps": link.bandwidth_mbps,
                    "latency_ms": link.latency_ms,
                    "packet_loss": link.packet_loss,
                    "utilization": network.link_utilization.get(key),
                }
            )
        return {
            "round": network.now,
            "controlMessages": self.control_messages,
            "converged": self.converged,
            "config": describe_options(self.options, resolve_config(self.config)["profile"]),
            "routers": routers,
            "links": links,
        }


def _utilization_keys(network: RipNetwork, report) -> dict[frozenset[str], float]:
    by_label = {"-".join(sorted(key)): key for key in network.links}
    return {by_label[label]: value for label, value in report.link_utilization.items()}


class RipxRequestHandler(SimpleHTTPRequestHandler):
    session: EngineSession

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - signature from base class
        pass

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1_000_000:
            raise ApiError("request body too large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError as error:
            raise ApiError(f"invalid JSON: {error.msg}") from error
        if not isinstance(payload, dict):
            raise ApiError("request body must be a JSON object")
        return payload

    @staticmethod
    def _start_benchmark(body: dict[str, Any]) -> dict[str, Any]:
        seeds = int(body.get("seeds", 5))
        if not 2 <= seeds <= 30:
            raise ApiError("seeds must be between 2 and 30")
        return {"started": BENCHMARK_JOB.start(seeds), **BENCHMARK_JOB.status()}

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        if self.path == "/api/health":
            self._send_json({"engine": "python", "name": "ripx"})
            return
        if self.path == "/api/state":
            with self.session.lock:
                try:
                    self._send_json(self.session.snapshot())
                except ApiError as error:
                    self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/benchmark/latest":
            self._send_json(latest_benchmark())
            return
        if self.path == "/api/benchmark/status":
            self._send_json(BENCHMARK_JOB.status())
            return
        if self.path.startswith("/api/"):
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        routes = {
            "/api/network": lambda body: self.session.build(body),
            "/api/step": lambda body: self.session.step(int(body.get("rounds", 1))),
            "/api/converge": lambda body: self.session.converge(int(body.get("max_rounds", 200))),
            "/api/router/toggle": lambda body: self.session.toggle_router(str(body.get("router", ""))),
            "/api/link/toggle": lambda body: self.session.toggle_link(str(body.get("u", "")), str(body.get("v", ""))),
            "/api/link/conditions": lambda body: self.session.set_link(body),
            "/api/trace": lambda body: self.session.trace(str(body.get("source", "")), str(body.get("destination", ""))),
            "/api/traffic": lambda body: self.session.traffic(body),
        }
        stateless = {
            "/api/compare": compare,
            "/api/demo/traffic": traffic_demo,
            "/api/benchmark/run": self._start_benchmark,
        }
        if self.path in stateless:
            try:
                self._send_json(stateless[self.path](self._read_json()))
            except (ApiError, TypeError, ValueError) as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        handler = routes.get(self.path)
        if handler is None:
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            body = self._read_json()
            with self.session.lock:
                result = handler(body)
        except (ApiError, TypeError, ValueError) as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        self._send_json(result)


def create_server(host: str = "127.0.0.1", port: int = 8080, directory: Path = VISUALIZER_DIR) -> ThreadingHTTPServer:
    """Build (but do not start) a server bound to ``host:port``; port 0 picks a free port."""
    session = EngineSession()
    handler = partial(type("Handler", (RipxRequestHandler,), {"session": session}), directory=str(directory))
    return ThreadingHTTPServer((host, port), handler)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve the RIP-X visualizer backed by the Python engine.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--open", action="store_true", help="open the visualizer in a browser")
    arguments = parser.parse_args(argv)
    server = create_server(arguments.host, arguments.port)
    url = f"http://{arguments.host}:{server.server_address[1]}"
    print(f"RIP-X visualizer (Python engine) running at {url} — press Ctrl+C to stop.")
    if arguments.open:
        import webbrowser

        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
