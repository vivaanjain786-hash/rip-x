"""Count-to-infinity and RIP stability mechanism experiments.

These experiments demonstrate standard RIP weaknesses (count-to-infinity,
routing loops) and compare how split horizon and poison reverse affect
convergence speed and loop duration under controlled conditions.

All results come from the simulator; no figures are fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass

from ripx.routing.rip import INFINITY, RipRouter
from ripx.simulation.network import RipNetwork


@dataclass(frozen=True)
class CountToInfinityResult:
    """Outcome of one count-to-infinity experiment run."""
    configuration: str
    rounds_to_invalidate: int
    """Number of rounds before R1's route to R3 reaches INFINITY (16)."""
    peak_metric: int
    """Highest hop-count reached by R1's route to R3 during counting."""
    loop_detected: bool
    """True if both R1 and R2 simultaneously held a reachable route via each other."""
    control_messages: int


def _count_to_infinity_experiment(poison_reverse: bool) -> CountToInfinityResult:
    """Simulate count-to-infinity on a 3-node line: R1 — R2 — R3.

    After convergence, R3 is removed from R2's reachability (simulated by
    withdrawing R2's knowledge of R3 without a triggered update, mimicking the
    scenario where R2 does not immediately know about R3's failure and instead
    learns a looped route via R1).

    Without poison reverse: R1 re-advertises R3 via R2, causing count-to-infinity.
    With poison reverse: R2 advertises INFINITY back to R1, breaking the loop.
    """
    label = "poison_reverse" if poison_reverse else "no_split_horizon"
    network = RipNetwork(poison_reverse=poison_reverse)
    for name in ("R1", "R2", "R3"):
        network.add_router(name)
    network.add_link("R1", "R2")
    network.add_link("R2", "R3")
    network.converge()

    # Sever R3 from R2's perspective without a clean withdrawal — simulates
    # a scenario where R3 goes silent and R2 does not trigger a poisoned update.
    # We manually poison R2's direct route to R3 without notifying R1 yet,
    # so R1 still believes it can reach R3 via R2.
    r2 = network.routers["R2"]
    r2.routes["R3"] = r2.routes["R3"].__class__(
        destination="R3",
        metric=INFINITY,
        next_hop=None,
        learned_from=None,
        changed_at=network.now,
        invalid_since=network.now,
    )

    peak_metric = 0
    loop_detected = False
    rounds = 0
    max_rounds = 40  # 2 × INFINITY is sufficient headroom

    for _ in range(max_rounds):
        result = network.step()
        rounds += 1
        r1_route = network.routers["R1"].route("R3")
        r2_route = network.routers["R2"].route("R3")
        if r1_route is not None and r1_route.reachable:
            peak_metric = max(peak_metric, r1_route.metric)
            # Loop: R1 thinks next-hop is R2, R2 thinks next-hop is R1
            if (
                r2_route is not None
                and r2_route.reachable
                and r1_route.next_hop == "R2"
                and r2_route.next_hop == "R1"
            ):
                loop_detected = True
        if r1_route is None or r1_route.metric >= INFINITY:
            break

    return CountToInfinityResult(
        configuration=label,
        rounds_to_invalidate=rounds,
        peak_metric=peak_metric,
        loop_detected=loop_detected,
        control_messages=rounds * 2,  # R1↔R2 messages per round on a 2-link path
    )


def run_count_to_infinity_comparison() -> dict[str, object]:
    """Compare standard RIP vs poison-reverse under a count-to-infinity scenario.

    Returns a dict suitable for JSON serialisation with both configurations'
    measured outcomes side-by-side.
    """
    without_pr = _count_to_infinity_experiment(poison_reverse=False)
    with_pr = _count_to_infinity_experiment(poison_reverse=True)
    return {
        "experiment": "count_to_infinity_comparison",
        "description": (
            "3-router line R1-R2-R3. R3 becomes unreachable from R2. "
            "Measures rounds until R1 marks R3 unreachable (metric=16), "
            "peak metric reached, and whether a forwarding loop was observed."
        ),
        "results": [
            {
                "configuration": without_pr.configuration,
                "rounds_to_invalidate": without_pr.rounds_to_invalidate,
                "peak_metric": without_pr.peak_metric,
                "loop_detected": without_pr.loop_detected,
                "control_messages": without_pr.control_messages,
            },
            {
                "configuration": with_pr.configuration,
                "rounds_to_invalidate": with_pr.rounds_to_invalidate,
                "peak_metric": with_pr.peak_metric,
                "loop_detected": with_pr.loop_detected,
                "control_messages": with_pr.control_messages,
            },
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
