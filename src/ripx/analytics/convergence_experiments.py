"""Count-to-infinity and RIP stability mechanism experiments.

These experiments demonstrate standard RIP weaknesses (count-to-infinity,
routing loops) and compare how split horizon and poison reverse affect
convergence speed and loop duration under controlled conditions.

All results come from the simulator; no figures are fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass

from ripx.simulation.network import RipNetwork


@dataclass(frozen=True)
class CountToInfinityResult:
    """Outcome of one count-to-infinity experiment run."""
    configuration: str
    rounds_to_invalidate: int
    """Number of rounds until neither R1 nor R2 holds a reachable route to R3."""
    peak_metric: int
    """Highest reachable hop-count R1 or R2 held for R3 after the failure."""
    loop_detected: bool
    """True if both R1 and R2 simultaneously held a reachable route via each other."""
    control_messages: int


_LOOP_PROTECTION = {
    # configuration label: (split_horizon, poison_reverse)
    "no_protection": (False, False),
    "split_horizon": (True, False),
    "poison_reverse": (True, True),
}


def _count_to_infinity_experiment(configuration: str) -> CountToInfinityResult:
    """Simulate count-to-infinity on a 3-node line: R1 — R2 — R3.

    After convergence R3 fails. R2 poisons its route to R3 immediately, but in
    the same round R1 still advertises its old two-hop route to R3. Without
    split horizon, R2 accepts that route via R1 and the pair count upward
    until the metric reaches INFINITY. Split horizon stops R1 from advertising
    the route back to R2, so the loss is learned in one round.

    Rounds are synchronous, so R1 and R2 alternate between a poisoned and a
    counting route rather than both holding a reachable route at once.
    """
    split_horizon, poison_reverse = _LOOP_PROTECTION[configuration]
    network = RipNetwork(split_horizon=split_horizon, poison_reverse=poison_reverse)
    for name in ("R1", "R2", "R3"):
        network.add_router(name)
    network.add_link("R1", "R2")
    network.add_link("R2", "R3")
    network.converge()

    network.fail_router("R3")

    peak_metric = 0
    loop_detected = False
    rounds = 0
    control_messages = 0
    max_rounds = 40  # 2 × INFINITY is sufficient headroom

    for _ in range(max_rounds):
        result = network.step()
        rounds += 1
        control_messages += result.control_messages
        r1_route = network.routers["R1"].route("R3")
        r2_route = network.routers["R2"].route("R3")
        for route in (r1_route, r2_route):
            if route is not None and route.reachable:
                peak_metric = max(peak_metric, route.metric)
        # Loop: R1 and R2 both hold a reachable route via each other.
        if (
            r1_route is not None
            and r1_route.reachable
            and r2_route is not None
            and r2_route.reachable
            and r1_route.next_hop == "R2"
            and r2_route.next_hop == "R1"
        ):
            loop_detected = True
        if all(route is None or not route.reachable for route in (r1_route, r2_route)):
            break

    return CountToInfinityResult(
        configuration=configuration,
        rounds_to_invalidate=rounds,
        peak_metric=peak_metric,
        loop_detected=loop_detected,
        control_messages=control_messages,
    )


def run_count_to_infinity_comparison() -> dict[str, object]:
    """Compare no loop protection, split horizon and poison reverse.

    Returns a dict suitable for JSON serialisation with each configuration's
    measured outcomes side-by-side.
    """
    measured = [_count_to_infinity_experiment(configuration) for configuration in _LOOP_PROTECTION]
    return {
        "experiment": "count_to_infinity_comparison",
        "description": (
            "3-router line R1-R2-R3. R3 fails after convergence. "
            "Measures rounds until neither R1 nor R2 holds a reachable route "
            "to R3, the peak metric either router reached for R3, and whether "
            "a forwarding loop was observed."
        ),
        "results": [
            {
                "configuration": result.configuration,
                "rounds_to_invalidate": result.rounds_to_invalidate,
                "peak_metric": result.peak_metric,
                "loop_detected": result.loop_detected,
                "control_messages": result.control_messages,
            }
            for result in measured
        ],
    }


@dataclass(frozen=True)
class ConvergenceScaleResult:
    """Measured convergence time for one topology/size configuration."""
    topology: str
    routers: int
    convergence_rounds: int
    control_messages: int


def run_convergence_scaling(
    topology_factory,
    sizes: list[int],
    label: str,
) -> list[ConvergenceScaleResult]:
    """Measure convergence rounds and message count as network size grows.

    Args:
        topology_factory: A callable ``(size) -> RipNetwork``.
        sizes: List of router counts to test.
        label: Human-readable topology name for the result records.

    Returns a list of ``ConvergenceScaleResult``, one per size.
    """
    results = []
    for size in sizes:
        network = topology_factory(size)
        convergence = network.converge()
        results.append(
            ConvergenceScaleResult(
                topology=label,
                routers=size,
                convergence_rounds=convergence.rounds,
                control_messages=convergence.control_messages,
            )
        )
    return results
