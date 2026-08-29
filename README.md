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

Scenario files are JSON with a name, a baseline topology (`line`, `ring`, `star`, `mesh`, or `random`), and a router count. Random scenarios also accept a seed and edge probability. Reports capture only measured simulator values; RIP-X makes no performance claims from unrun experiments.

Failure scenarios can also contain ordered `router_failure`, `router_recovery`, `link_failure`, and `link_recovery` events. Each event produces a separate measured re-convergence phase.

Link impairment events (`packet_loss_spike`, `latency_spike`, and `link_restore`) change telemetry and traffic delivery while standard RIP continues using hop-count routes.

Traffic scenarios add `flows` with a source, destination, and offered `rate_mbps`. Each experiment phase reports delivered, dropped, and unroutable traffic along with bottleneck links and maximum utilization.

## Scope

RIP remains the routing foundation. RIP-X is a research simulator for small, controlled networks; it does not replace OSPF, BGP, or public-Internet routing.

For a short review presentation, run [the RIP failure-and-recovery demo](docs/review-demo.md).
