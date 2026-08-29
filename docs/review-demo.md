# Review 1 demonstration

## Run the demonstration

```bash
python -m pip install -e .
python examples/review_demo.py
```

The demo uses a five-router ring. It first converges with standard RIP, then
injects a failure of router `R2`, and finally recovers that router.

## What to explain

1. RIP-X keeps RIP's distributed distance-vector model; it does not use
   Dijkstra for route selection.
2. A route contains a hop-count metric and next hop. Metric 16 represents an
   unreachable route.
3. When `R2` fails, its neighbors poison dependent routes. The remaining ring
   provides an alternate route from `R1` to `R3` through `R5` and `R4`.
4. When `R2` returns, RIP exchanges vectors again and the shorter route is
   selected.
5. The printed convergence rounds and control messages are measured by this
   simulation run, not estimated results.

## Current limitation

This is a discrete-round research simulator. It currently measures routing
convergence and control messages; traffic, congestion, and optimization are
planned later phases.
