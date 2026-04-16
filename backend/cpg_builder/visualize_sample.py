from __future__ import annotations

import argparse
from pathlib import Path

import networkx as nx


def main() -> int:
    parser = argparse.ArgumentParser(description="Quick CPG visualization helper.")
    parser.add_argument("graphml", help="Path to a GraphML CPG export")
    parser.add_argument("--limit", type=int, default=150, help="Maximum nodes to draw")
    args = parser.parse_args()

    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ImportError("matplotlib is required for the sample visualization script") from exc

    graph = nx.read_graphml(Path(args.graphml))
    if graph.number_of_nodes() > args.limit:
        keep = list(graph.nodes())[: args.limit]
        graph = graph.subgraph(keep).copy()

    pos = nx.spring_layout(graph, seed=42)
    plt.figure(figsize=(14, 10))
    nx.draw_networkx(
        graph,
        pos=pos,
        with_labels=False,
        node_size=70,
        arrows=True,
        width=0.5,
    )
    plt.title("CPG sample view")
    plt.tight_layout()
    plt.show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
