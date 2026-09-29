# RIP-X architecture

RIP-X is a layer on top of the baseline RIP simulator ([baseline.md](baseline.md)). Every RIP-X feature is off by default, and the defaults reproduce the original baseline byte for byte (checked against all bundled scenario outputs). A configuration turns features on; nothing in the baseline code path is replaced.

## The hypothesis

> An adaptive update policy can reduce control-message overhead in stable networks while keeping convergence after topology changes close to standard RIP. Congestion-aware link costs, applied by a bounded traffic-engineering loop, can raise delivered traffic when hop-count routing overloads a link.

The benchmark ([results/benchmark/report.md](../../results/benchmark/report.md)) tests both halves and reports where the hypothesis does not hold.

## Components

| Component | File | What it does |
|---|---|---|
| Loop protection modes | `routing/rip.py` | `split_horizon` and `poison_reverse` are independent switches, so a true no-protection network (count-to-infinity) can be simulated. |
| Update schedules | `routing/scheduling.py` | `FixedUpdateSchedule` is standard RIP. `AdaptiveUpdateSchedule` gives each router its own periodic interval: it doubles (up to a cap) after a periodic update sent while the router's table was unchanged, and resets to the minimum when any route changes. |
| Triggered updates | `simulation/network.py` | Between periodic rounds a router advertises only if it has a pending change. Independent of the schedule. |
| Route requests | `simulation/network.py` (`request_on_loss`) | A router that loses a reachable route asks its neighbors for their full tables, so an alternative path is heard without waiting for the neighbors' next periodic update. This is what keeps adaptive intervals from slowing down repair. |
| Link-cost policies | `routing/metrics.py` | `HopCountCost` is standard RIP (cost 1). `CongestionAwareCost` charges 1 plus a penalty per utilization threshold reached, plus one for high latency and one for high loss, capped at `max_cost` (default 3) because RIP's metric still saturates at 16. Utilization penalties have hysteresis so a link near a threshold does not flap. |
| Traffic engineering | `simulation/traffic_engineering.py` | Measure traffic on current routes, raise the cost of congested links, let RIP re-converge, repeat for at most `max_epochs`. The epoch with the most delivered traffic (then lowest peak utilization) is installed and re-measured. |
| Configuration | `config.py` | Named profiles (`baseline`, `rip`, `ripx`) and the `rip` object accepted by scenario files. |
| Validation | `analytics/validation.py` | Bellman-Ford over the network's current link costs; counts incorrect, black-holed, looping and stale routes each round. |
| Benchmark | `analytics/benchmark.py`, `benchmark.py` | Controlled comparison; see below. |
| Live engine | `server.py` | JSON API over `RipNetwork` that drives the browser visualizer. |

## Scenario settings

```json
{
  "name": "example",
  "topology": "ring",
  "routers": 6,
  "rip": {"profile": "ripx", "request_on_loss": true},
  "links": [{"link": ["R1", "R2"], "bandwidth_mbps": 50}],
  "traffic_engineering": {"max_epochs": 10},
  "flows": [{"source": "R1", "destination": "R3", "rate_mbps": 70}]
}
```

`rip` accepts `profile`, `updates`, `metric`, `split_horizon`, `poison_reverse`, `triggered_updates`, `request_on_loss`, `route_timeout` and `garbage_collection`. Explicit keys override the profile. See `scenarios/ripx-traffic-engineering-ring.json`.

## Benchmark method

Two experiments, both seeded and reproducible (`python -m ripx.benchmark --seeds 30`):

1. **Update control.** Random connected topologies (20 routers). After initial convergence: 100 stable rounds, a link failure, recovery, a router failure, recovery. The failed link and router are chosen per seed so the rest of the network stays connected, and every configuration sees the same failures. Each round the tables are compared with Bellman-Ford, so convergence time, black holes, loops and stale routes are measured. Four configurations: `rip`, `rip+requests`, `adaptive-only`, `ripx`, so the contribution of each part is visible.
2. **Traffic engineering.** Random topologies with mixed link capacities and random flows; delivered/offered traffic under hop-count RIP against the traffic-engineering loop.

Results give the mean, a 95% confidence interval (Student t), and paired differences against standard RIP on the same seed.

## Known limits

- **Single-path forwarding.** RIP keeps one next hop per destination, so all flows to the same destination from the same router move together. Traffic engineering helps when different flows can take different paths; it cannot split one flow pair across two paths.
- **Discrete rounds.** One round stands for about five seconds of RFC timers (the `rip` profile scales 30/180/120 s to 5/30/20 rounds). Messages are never lost and failures are detected immediately by both ends.
- **Accounting traffic model.** Traffic is measured, not packet-simulated.
- **Costs only rise within one traffic-engineering run.** This guarantees termination; costs are reset to load-free values at the start of each run.
- **Adaptive updates trade repair time for messages** unless route requests are on. The benchmark's `adaptive-only` column shows the cost of leaving them off.

## Findings (30 seeds; see `results/benchmark/report.md`)

Measured by `python -m ripx.benchmark --seeds 30`. Intervals are 95% confidence intervals of paired differences against standard RIP.

- **Adaptive updates cut control messages by about 61%** (9,976 → 3,876 per run; Δ −6,099 [−6,553, −5,646]) and by 65% in stable periods.
- **Convergence after a failure stays close to standard RIP only with route requests.** Adaptive updates alone slow link-failure repair from 3.0 to 15.7 rounds; with requests it is 2.2 rounds, and router-failure convergence improves (7.0 vs 12.3). The requests add about 3% messages on top of RIP.
- **The hypothesis does not fully hold.** RIP-X has *more* black-holed pair-rounds than RIP (58.8 vs 29.7, Δ +29.0 [17.8, 40.3]): a slower periodic schedule delays some repair of routes that requests do not cover. It has fewer looping and stale-route pair-rounds and less route churn.
- **Congestion-aware traffic engineering delivered more traffic in 24 of 30 trials and less in 2** (mean delivered ratio 0.686 → 0.786, Δ +0.100 [0.061, 0.138]), at the price of longer paths (+0.2 hops) and about 670 extra control messages per run.
