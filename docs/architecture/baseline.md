# Baseline architecture

RIP-X begins with a deterministic discrete-round simulator. Each round snapshots every router's distance vector, delivers vectors over active links, and then applies protocol timers. This avoids wall-clock timing and makes experiments repeatable.

The initial implementation has three deliberately separate concerns:

- `simulation`: routers, links, topology factories, and failure injection.
- `routing`: an independent Bellman-Ford correctness baseline and a RIP control-plane model.
- `analytics`: small, serializable experiment results.

RIP uses hop count only in this baseline. Links retain latency, bandwidth, and loss attributes as telemetry inputs for later measured extensions; none influence route selection yet.

The RIP implementation models maximum metric 16, triggered updates, split horizon with poison reverse, route poisoning after link loss, timeout, and garbage collection. It does not claim RFC interoperability: it is a controlled research simulator.
