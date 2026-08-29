"""Review demonstration: RIP convergence, router failure, and recovery.

Run after installing the project with ``python -m pip install -e .``:
    python examples/review_demo.py
"""

from __future__ import annotations

from ripx.simulation.topologies import ring


def describe_route(network, source: str, destination: str) -> str:
    route = network.routers[source].route(destination)
    if route is None:
        return f"{source} -> {destination}: removed after garbage collection"
    state = "reachable" if route.reachable else "unreachable"
    return (
        f"{source} -> {destination}: {state}, metric={route.metric}, "
        f"next_hop={route.next_hop}"
    )


def run_demo() -> None:
    network = ring(5)
    baseline = network.converge()
    print("RIP-X review demonstration")
    print("Topology: 5-router ring (R1-R2-R3-R4-R5-R1)")
    print(f"Baseline convergence: {baseline.rounds} rounds, {baseline.control_messages} control messages")
    print(describe_route(network, "R1", "R3"))

    network.fail_router("R2")
    after_failure = network.converge()
    print("\nInjected event: router R2 failure")
    print(f"Re-convergence: {after_failure.rounds} rounds, {after_failure.control_messages} control messages")
    print(describe_route(network, "R1", "R2"))
    print(describe_route(network, "R1", "R3"))

    network.recover_router("R2")
    after_recovery = network.converge()
    print("\nInjected event: router R2 recovery")
    print(f"Re-convergence: {after_recovery.rounds} rounds, {after_recovery.control_messages} control messages")
    print(describe_route(network, "R1", "R3"))


if __name__ == "__main__":
    run_demo()
