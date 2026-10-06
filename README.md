# RIP-X

RIP-X is a reproducible Python simulator for studying RIP-based distance-vector routing under controlled topology and failure scenarios. The project starts with a correct, testable RIP baseline before introducing telemetry, resilience, or optimization layers.

## Current baseline

- Deterministic line, ring, star, mesh, and seeded random topologies
- Router and link abstraction with bandwidth, latency, and packet-loss fields
- Bellman-Ford baseline for route validation
- RIP hop-count routing with maximum metric 16
- Split horizon with poison reverse, triggered updates, route poisoning, route timeout, and garbage collection
- Link and router failure/recovery injection
- RIP-path traffic accounting with per-link utilization and delivery metrics
- Structured telemetry for route reachability, route changes, link state, latency, loss, and utilization
- Reproducible convergence experiments and automated tests

## Quick start

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ripx scenarios/baseline-ring-10.json --output results/baseline-ring-10.json
```

## RIP-X

RIP-X extends the baseline with three mechanisms, all off by default (see [docs/architecture/ripx.md](docs/architecture/ripx.md)):

- **Adaptive update scheduling** — each router lengthens its periodic update interval while its table is stable, and drops back to the minimum on any change.
- **Route requests on loss** — a router that loses a route asks its neighbors for their tables so repair does not wait for the next periodic update.
- **Congestion-aware link costs and traffic engineering** — link cost grows with utilization, latency and loss, and a bounded loop steers flows off overloaded links.

Select them with `RipNetwork(schedule=..., cost_policy=..., request_on_loss=True)` or, in scenario files, `"rip": {"profile": "ripx"}` (profiles: `baseline`, `rip`, `ripx`).

### Benchmark

```bash
python -m pip install -e .        # once; the package lives in src/
python -m ripx.benchmark --seeds 30 --output results/benchmark
```

Runs the seeded RIP-vs-RIP-X comparison and writes `report.md`, JSON with every trial, and a plot. See [results/benchmark/report.md](results/benchmark/report.md) for the latest run.

## Live Interactive Visualizer (Packet Tracer Mode)

Run the real-time, browser-based Packet Tracer style simulator, driven by the Python RIP engine:

```bash
python run_live_simulator.py      # works straight from a fresh clone, nothing to install
# or, after `python -m pip install -e .`:
python -m ripx.server --open
```

The package lives in `src/ripx`, so `python -m ripx...` commands (including `python -m ripx.server` and `python -m ripx.benchmark`) need the one-time `python -m pip install -e .` first; without it Python reports `No module named 'ripx'`. `run_live_simulator.py` adds `src/` to the path itself. In a GitHub Codespace, use `python run_live_simulator.py --port 8080` and open the forwarded port from the Ports tab (the browser cannot be opened automatically there).

The **Dashboard** (`/dashboard.html`, linked from the top of the simulator) has one button per feature: a side-by-side standard RIP vs RIP-X run on identical failures with live message, repair-time, black-hole and loop counters and charts; a traffic-engineering demo; and the benchmark (saved results, or run a new one from the page).

The page shows `Engine: Python` when it is connected. Opening `visualizer/index.html` directly (without the server) falls back to a standalone in-browser engine that supports only baseline RIP. The Protocol Profile menu (baseline, standard RIP, RIP-X) and the Split Horizon toggle need the Python engine.

This launches the interactive canvas at `http://localhost:8080`, allowing you to:
- **Play / Step rounds**: Animate RIP advertisement packets flying along links.
- **Fault Injection**: Click any router to simulate node failures or sever links to see dynamic re-convergence.
- **Inspect Routing Tables**: Real-time distance-vector updates (metrics, next hops, reachability).
- **Inject Traffic**: Send data flows (e.g. $R_1 \to R_3$) and watch dynamic packet forwarding.

To generate the static 6-panel analytical dashboard image:
```bash
python examples/visualize.py --save results/dashboard.png
```

## Scenarios & Experiments

Scenario files are JSON with a name, a baseline topology (`line`, `ring`, `star`, `mesh`, or `random`), and a router count. Random scenarios also accept a seed and edge probability. Reports capture only measured simulator values; RIP-X makes no performance claims from unrun experiments.

Failure scenarios can also contain ordered `router_failure`, `router_recovery`, `link_failure`, and `link_recovery` events. Each event produces a separate measured re-convergence phase.

Scenario files also accept `rip` (protocol profile and settings), `links` (per-link bandwidth, latency, loss) and `traffic_engineering` (see the RIP-X section above). The count-to-infinity experiment (`run_count_to_infinity_comparison`) compares no protection, split horizon and poison reverse after a router failure.

Link impairment events (`packet_loss_spike`, `latency_spike`, and `link_restore`) change telemetry and traffic delivery while standard RIP continues using hop-count routes.

Traffic scenarios add `flows` with a source, destination, and offered `rate_mbps`. Each experiment phase reports delivered, dropped, and unroutable traffic along with bottleneck links and maximum utilization.

## Scope

RIP remains the routing foundation. RIP-X is a research simulator for small, controlled networks; it does not replace OSPF, BGP, or public-Internet routing.

For a short review presentation, run [the RIP failure-and-recovery demo](docs/review-demo.md).

