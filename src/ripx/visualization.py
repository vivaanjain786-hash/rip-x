"""RIP-X network visualization using NetworkX and Matplotlib.

Provides functions to draw:
 - network topology with link utilization heat-map
 - routing tables as annotated text
 - convergence time comparison bar charts
 - count-to-infinity metric progression
 - side-by-side failure/recovery topology states

All visualizations are purely measurement-driven from the simulator state.
No fabricated data is displayed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable

if TYPE_CHECKING:
    from ripx.simulation.network import RipNetwork

# ── Colour palette ────────────────────────────────────────────────────────────
_PALETTE = {
    "bg":          "#0f1117",
    "panel":       "#1a1d27",
    "node":        "#4c9be8",
    "node_failed": "#e84c4c",
    "node_text":   "#ffffff",
    "edge_ok":     "#2ecc71",
    "edge_down":   "#e84c4c",
    "accent":      "#f39c12",
    "text":        "#dce1ec",
    "grid":        "#2a2d3a",
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _apply_dark_style(fig: plt.Figure, axes) -> None:
    fig.patch.set_facecolor(_PALETTE["bg"])
    if hasattr(axes, "__iter__"):
        for ax in axes:
            _style_ax(ax)
    else:
        _style_ax(axes)


def _style_ax(ax: plt.Axes) -> None:
    ax.set_facecolor(_PALETTE["panel"])
    ax.tick_params(colors=_PALETTE["text"])
    ax.xaxis.label.set_color(_PALETTE["text"])
    ax.yaxis.label.set_color(_PALETTE["text"])
    ax.title.set_color(_PALETTE["text"])
    for spine in ax.spines.values():
        spine.set_edgecolor(_PALETTE["grid"])


def _build_nx_graph(network: "RipNetwork") -> tuple[nx.Graph, dict]:
    """Return a NetworkX undirected graph and a spring-layout position dict."""
    g = nx.Graph()
    g.add_nodes_from(sorted(network.routers.keys()))
    for link in network.links.values():
        g.add_edge(link.left, link.right, up=link.up,
                   latency=link.latency_ms, loss=link.packet_loss,
                   bw=link.bandwidth_mbps)
    pos = nx.spring_layout(g, seed=42, k=2.5)
    return g, pos


def _utilization_color(util: float | None) -> str:
    if util is None:
        return _PALETTE["edge_ok"]
    if util >= 1.0:
        return "#e84c4c"
    if util >= 0.7:
        return "#f39c12"
    return "#2ecc71"


# ── Public API ────────────────────────────────────────────────────────────────

def draw_topology(
    network: "RipNetwork",
    title: str = "RIP-X Network Topology",
    utilization: dict[str, float] | None = None,
    highlight_path: list[str] | None = None,
    ax: plt.Axes | None = None,
    show: bool = True,
) -> plt.Figure:
    """Draw the current network topology.

    Args:
        network:        A ``RipNetwork`` instance (after ``converge()`` if desired).
        title:          Figure / subplot title.
        utilization:    Optional link-label → fractional utilization dict
                        (from ``TrafficReport.link_utilization``).
        highlight_path: Optional list of router names forming a forwarding path
                        to highlight in the graph.
        ax:             Optional existing ``Axes`` to draw on.
        show:           Call ``plt.show()`` when True (set False when embedding).
    """
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(10, 7))
        _apply_dark_style(fig, ax)
    else:
        fig = ax.get_figure()

    g, pos = _build_nx_graph(network)

    # Node colours
    node_colors = [
        _PALETTE["node_failed"] if n in network.failed_routers else _PALETTE["node"]
        for n in g.nodes()
    ]

    # Edge colours / widths
    edge_colors, edge_widths = [], []
    for u, v, data in g.edges(data=True):
        label = "-".join(sorted((u, v)))
        util = utilization.get(label) if utilization else None
        is_down = not data.get("up", True) or u in network.failed_routers or v in network.failed_routers
        if is_down:
            edge_colors.append(_PALETTE["edge_down"])
            edge_widths.append(1.0)
        else:
            edge_colors.append(_utilization_color(util))
            edge_widths.append(2.5)

    nx.draw_networkx(
        g, pos=pos, ax=ax,
        node_color=node_colors,
        edge_color=edge_colors,
        width=edge_widths,
        node_size=700,
        font_size=8,
        font_color=_PALETTE["node_text"],
        font_weight="bold",
    )

    # Highlight forwarding path
    if highlight_path and len(highlight_path) > 1:
        path_edges = list(zip(highlight_path, highlight_path[1:]))
        nx.draw_networkx_edges(
            g, pos=pos, ax=ax,
            edgelist=path_edges,
            edge_color=_PALETTE["accent"],
            width=5.0,
            style="solid",
            alpha=0.9,
        )

    # Utilization edge labels
    if utilization:
        edge_labels = {}
        for u, v in g.edges():
            label = "-".join(sorted((u, v)))
            if label in utilization:
                edge_labels[(u, v)] = f"{utilization[label]:.0%}"
        nx.draw_networkx_edge_labels(
            g, pos=pos, ax=ax, edge_labels=edge_labels,
            font_size=7, font_color=_PALETTE["accent"],
            bbox=dict(boxstyle="round,pad=0.2", fc=_PALETTE["panel"], ec="none", alpha=0.8),
        )

    # Legend
    legend_items = [
        mpatches.Patch(color=_PALETTE["node"], label="Router (up)"),
        mpatches.Patch(color=_PALETTE["node_failed"], label="Router (failed)"),
        mpatches.Patch(color="#2ecc71", label="Link < 70% util"),
        mpatches.Patch(color="#f39c12", label="Link 70–99% util"),
        mpatches.Patch(color="#e84c4c", label="Link ≥ 100% / down"),
    ]
    if highlight_path:
        legend_items.append(mpatches.Patch(color=_PALETTE["accent"], label="Forwarding path"))
    ax.legend(handles=legend_items, loc="lower left",
              facecolor=_PALETTE["panel"], edgecolor=_PALETTE["grid"],
              labelcolor=_PALETTE["text"], fontsize=8)

    ax.set_title(title, color=_PALETTE["text"], fontsize=13, pad=12)
    ax.axis("off")

    if standalone and show:
        plt.tight_layout()
        plt.show()
    return fig


def draw_routing_table(
    network: "RipNetwork",
    router_name: str,
    ax: plt.Axes | None = None,
    show: bool = True,
) -> plt.Figure:
    """Display the routing table of one router as a formatted table."""
    from ripx.routing.rip import INFINITY
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(8, 5))
        _apply_dark_style(fig, ax)
    else:
        fig = ax.get_figure()

    router = network.routers[router_name]
    rows, colors = [], []
    for dest in sorted(router.routes):
        route = router.routes[dest]
        state = "reachable" if route.reachable else "UNREACHABLE"
        metric_str = str(route.metric) if route.metric < INFINITY else "∞ (16)"
        nh = route.next_hop or "—"
        lf = route.learned_from or "self"
        rows.append([dest, metric_str, nh, lf, state])
        if not route.reachable:
            colors.append(["#3a1a1a"] * 5)
        elif dest == router_name:
            colors.append(["#1a2a3a"] * 5)
        else:
            colors.append([_PALETTE["panel"]] * 5)

    col_labels = ["Destination", "Metric", "Next Hop", "Learned From", "Status"]
    if not rows:
        ax.text(0.5, 0.5, "No routes", ha="center", va="center",
                color=_PALETTE["text"], fontsize=12)
    else:
        tbl = ax.table(
            cellText=rows,
            colLabels=col_labels,
            cellColours=colors,
            cellLoc="center",
            loc="center",
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(9)
        tbl.scale(1, 1.6)
        for (row, col), cell in tbl.get_celld().items():
            cell.set_edgecolor(_PALETTE["grid"])
            if row == 0:
                cell.set_facecolor("#252840")
                cell.set_text_props(color=_PALETTE["accent"], fontweight="bold")
            else:
                cell.set_text_props(color=_PALETTE["text"])

    ax.set_title(f"Routing Table — {router_name}  (round {network.now})",
                 color=_PALETTE["text"], fontsize=12, pad=10)
    ax.axis("off")

    if standalone and show:
        plt.tight_layout()
        plt.show()
    return fig


def draw_convergence_bar(
    results: list[dict],
    title: str = "RIP Convergence Rounds by Topology",
    ax: plt.Axes | None = None,
    show: bool = True,
) -> plt.Figure:
    """Bar chart of convergence rounds for a list of experiment result dicts.

    Each dict must have ``topology``, ``routers``, and ``convergence_rounds``.
    """
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(10, 5))
        _apply_dark_style(fig, ax)
    else:
        fig = ax.get_figure()

    labels = [f"{r['topology']}\n({r['routers']} routers)" for r in results]
    rounds = [r["convergence_rounds"] for r in results]
    msgs = [r.get("control_messages", 0) for r in results]

    x = range(len(results))
    bars = ax.bar(x, rounds, color=_PALETTE["node"], width=0.5, label="Convergence rounds")
    ax.bar(x, [m / max(msgs or [1]) * max(rounds or [1]) for m in msgs],
           color=_PALETTE["accent"], width=0.5, alpha=0.4, label="Control messages (scaled)")

    for bar, val in zip(bars, rounds):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                str(val), ha="center", va="bottom", color=_PALETTE["text"], fontsize=9)

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, color=_PALETTE["text"], fontsize=9)
    ax.set_ylabel("Rounds", color=_PALETTE["text"])
    ax.set_title(title, color=_PALETTE["text"], fontsize=13)
    ax.yaxis.grid(True, color=_PALETTE["grid"], linestyle="--", alpha=0.5)
    ax.legend(facecolor=_PALETTE["panel"], edgecolor=_PALETTE["grid"],
              labelcolor=_PALETTE["text"])
    ax.set_ylim(0, max(rounds or [1]) * 1.3)

    if standalone and show:
        plt.tight_layout()
        plt.show()
    return fig


def draw_count_to_infinity(
    comparison: dict,
    ax: plt.Axes | None = None,
    show: bool = True,
) -> plt.Figure:
    """Bar chart comparing count-to-infinity experiment results.

    ``comparison`` is the return value of ``run_count_to_infinity_comparison()``.
    """
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(8, 5))
        _apply_dark_style(fig, ax)
    else:
        fig = ax.get_figure()

    results = comparison["results"]
    configs = [r["configuration"].replace("_", " ") for r in results]
    rounds = [r["rounds_to_invalidate"] for r in results]
    peaks  = [r["peak_metric"] for r in results]
    loops  = [r["loop_detected"] for r in results]

    x = range(len(results))
    width = 0.35
    b1 = ax.bar([xi - width / 2 for xi in x], rounds, width,
                color=_PALETTE["node"], label="Rounds to invalidate R3")
    b2 = ax.bar([xi + width / 2 for xi in x], peaks, width,
                color=_PALETTE["accent"], label="Peak metric reached")

    for bar, val in zip(b1, rounds):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                str(val), ha="center", color=_PALETTE["text"], fontsize=9)
    for bar, val, loop in zip(b2, peaks, loops):
        tag = f"{val}\n(loop!)" if loop else str(val)
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                tag, ha="center", color=_PALETTE["text"], fontsize=9)

    ax.set_xticks(list(x))
    ax.set_xticklabels(configs, color=_PALETTE["text"])
    ax.set_ylabel("Rounds / Metric value", color=_PALETTE["text"])
    ax.set_title("Count-to-Infinity: Standard RIP vs Poison Reverse\n(3-router line, R3 goes silent)",
                 color=_PALETTE["text"], fontsize=12)
    ax.yaxis.grid(True, color=_PALETTE["grid"], linestyle="--", alpha=0.5)
    ax.legend(facecolor=_PALETTE["panel"], edgecolor=_PALETTE["grid"],
              labelcolor=_PALETTE["text"])

    if standalone and show:
        plt.tight_layout()
        plt.show()
    return fig


def draw_failure_comparison(
    network_before: "RipNetwork",
    network_after: "RipNetwork",
    title_before: str = "Before Failure",
    title_after: str = "After Failure",
    show: bool = True,
) -> plt.Figure:
    """Side-by-side topology draw: state before and after a failure event."""
    fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(16, 7))
    _apply_dark_style(fig, [ax_left, ax_right])
    draw_topology(network_before, title=title_before, ax=ax_left, show=False)
    draw_topology(network_after,  title=title_after,  ax=ax_right, show=False)
    fig.suptitle("RIP-X Network — Failure Comparison",
                 color=_PALETTE["text"], fontsize=15, fontweight="bold", y=1.01)
    if show:
        plt.tight_layout()
        plt.show()
    return fig
