"""RIP-X visual dashboard demo.

Generates a 6-panel figure demonstrating the simulator's key results:

  Panel 1 — Ring-5 topology at baseline (no failures)
  Panel 2 — Ring-5 topology after R2 failure (routing rerouted via R5)
  Panel 3 — Routing table of R1 after R2 failure
  Panel 4 — Convergence rounds: line vs ring vs star vs mesh
  Panel 5 — Count-to-infinity comparison (standard vs poison reverse)
  Panel 6 — Scale-free topology (10 routers, seed 0)

All data is measured from the simulator — nothing is fabricated.

Run from the repository root:
    python examples/visualize.py

Or save to file:
    python examples/visualize.py --save results/dashboard.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import matplotlib
# Use Agg (file-only, no display needed) when --save is passed;
# fall back to the system default for interactive display.
_save_mode = "--save" in sys.argv
matplotlib.use("Agg" if _save_mode else matplotlib.get_backend())
import matplotlib.pyplot as plt

from ripx.analytics.convergence_experiments import run_count_to_infinity_comparison
from ripx.analytics.experiment import run_convergence_experiment
from ripx.simulation.topologies import ring, scale_free
from ripx.simulation.traffic import TrafficFlow, simulate_traffic
from ripx.visualization import (
    draw_convergence_bar,
    draw_count_to_infinity,
    draw_routing_table,
    draw_topology,
    _apply_dark_style,
    _PALETTE,
)

_BG = _PALETTE["bg"]
_TEXT = _PALETTE["text"]


def build_dashboard(save_path: str | None = None) -> None:
    # ── 1. Baseline ring-5 ────────────────────────────────────────────────────
    net_ring = ring(5)
    net_ring.converge()
    flows = [TrafficFlow("R1", "R3", 60.0), TrafficFlow("R2", "R5", 80.0)]
    traffic = simulate_traffic(net_ring, flows)
    path_r1_r3 = net_ring.route_path("R1", "R3")

    # ── 2. Ring-5 after R2 failure ────────────────────────────────────────────
    import copy, pickle
    net_failed = ring(5)
    net_failed.converge()
    net_failed.fail_router("R2")
    net_failed.converge()
    path_after = net_failed.route_path("R1", "R3")

    # ── 3. Convergence comparison ─────────────────────────────────────────────
    conv_results = [
        run_convergence_experiment("line",  8),
        run_convergence_experiment("ring",  8),
        run_convergence_experiment("star",  8),
        run_convergence_experiment("mesh",  8),
        run_convergence_experiment("line", 15),
        run_convergence_experiment("ring", 15),
    ]

    # ── 4. Count-to-infinity ──────────────────────────────────────────────────
    cti = run_count_to_infinity_comparison()

    # ── 5. Scale-free 10 ──────────────────────────────────────────────────────
    net_sf = scale_free(10, seed=0)
    net_sf.converge()

    # ── Build figure ──────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(20, 13), facecolor=_BG)
    fig.suptitle(
        "RIP-X  ·  Adaptive RIP-Based Routing Simulator  ·  Results Dashboard",
        color=_TEXT, fontsize=16, fontweight="bold", y=0.98,
    )

    gs = fig.add_gridspec(2, 3, hspace=0.45, wspace=0.35,
                          left=0.04, right=0.97, top=0.93, bottom=0.05)

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[0, 2])
    ax4 = fig.add_subplot(gs[1, 0])
    ax5 = fig.add_subplot(gs[1, 1])
    ax6 = fig.add_subplot(gs[1, 2])

    for ax in (ax1, ax2, ax3, ax4, ax5, ax6):
        ax.set_facecolor(_PALETTE["panel"])
        for spine in ax.spines.values():
            spine.set_edgecolor(_PALETTE["grid"])
        ax.tick_params(colors=_TEXT)
        ax.xaxis.label.set_color(_TEXT)
        ax.yaxis.label.set_color(_TEXT)
        ax.title.set_color(_TEXT)

    # Panel 1 — baseline ring with traffic
    draw_topology(
        net_ring,
        title="5-Router Ring — Baseline\n(traffic flows shown, R1→R3 path highlighted)",
        utilization=traffic.link_utilization,
        highlight_path=path_r1_r3,
        ax=ax1, show=False,
    )

    # Panel 2 — post-failure ring
    draw_topology(
        net_failed,
        title="5-Router Ring — After R2 Failure\n(R1→R3 reroutes via R5)",
        highlight_path=path_after,
        ax=ax2, show=False,
    )

    # Panel 3 — routing table of R1 post-failure
    draw_routing_table(net_failed, "R1", ax=ax3, show=False)
    ax3.set_title("R1 Routing Table — After R2 Failure\n(metric=16 = unreachable via R2)",
                  color=_TEXT, fontsize=10, pad=8)

    # Panel 4 — convergence bar
    draw_convergence_bar(conv_results, title="Convergence Rounds by Topology & Size",
                         ax=ax4, show=False)

    # Panel 5 — count-to-infinity
    draw_count_to_infinity(cti, ax=ax5, show=False)

    # Panel 6 — scale-free topology
    draw_topology(
        net_sf,
        title="Scale-Free Topology (10 routers)\nBarabási–Albert, seed=0",
        ax=ax6, show=False,
    )

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=_BG)
        print(f"Dashboard saved -> {save_path}")
    else:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="RIP-X visual dashboard")
    parser.add_argument("--save", metavar="PATH", help="save figure to file instead of displaying")
    args = parser.parse_args()
    build_dashboard(save_path=args.save)


if __name__ == "__main__":
    main()
