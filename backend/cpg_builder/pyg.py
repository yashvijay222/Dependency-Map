from __future__ import annotations

from typing import Any

import networkx as nx


def cpg_to_pyg(graph: nx.MultiDiGraph) -> dict[str, Any]:
    try:
        import torch
    except ImportError as exc:
        raise ImportError(
            "torch is required to convert a CPG to PyTorch Geometric tensors"
        ) from exc

    node_ids = list(graph.nodes())
    node_index = {node_id: idx for idx, node_id in enumerate(node_ids)}

    node_labels = sorted({str(graph.nodes[n].get("label", "UNKNOWN")) for n in node_ids})
    node_label_index = {label: idx for idx, label in enumerate(node_labels)}
    edge_labels = sorted(
        {
            str(attrs.get("label", "UNKNOWN"))
            for _, _, _, attrs in graph.edges(keys=True, data=True)
        },
    )
    edge_label_index = {label: idx for idx, label in enumerate(edge_labels)}
    categories = sorted({str(graph.nodes[n].get("category", "unknown")) for n in node_ids})
    category_index = {label: idx for idx, label in enumerate(categories)}

    x = torch.tensor(
        [
            [
                node_label_index[str(graph.nodes[node_id].get("label", "UNKNOWN"))],
                category_index[str(graph.nodes[node_id].get("category", "unknown"))],
            ]
            for node_id in node_ids
        ],
        dtype=torch.long,
    )

    edge_pairs: list[list[int]] = [[], []]
    edge_type_values: list[int] = []
    for src, dst, _key, attrs in graph.edges(keys=True, data=True):
        edge_pairs[0].append(node_index[src])
        edge_pairs[1].append(node_index[dst])
        edge_type_values.append(edge_label_index[str(attrs.get("label", "UNKNOWN"))])

    edge_index = (
        torch.tensor(edge_pairs, dtype=torch.long)
        if edge_type_values
        else torch.empty((2, 0), dtype=torch.long)
    )
    edge_type = (
        torch.tensor(edge_type_values, dtype=torch.long)
        if edge_type_values
        else torch.empty((0,), dtype=torch.long)
    )
    node_type = torch.tensor(
        [
            node_label_index[str(graph.nodes[node_id].get("label", "UNKNOWN"))]
            for node_id in node_ids
        ],
        dtype=torch.long,
    )

    return {
        "x": x,
        "edge_index": edge_index,
        "edge_type": edge_type,
        "node_type": node_type,
        "node_ids": node_ids,
        "node_feature_dicts": [dict(graph.nodes[node_id]) for node_id in node_ids],
        "node_label_vocab": node_label_index,
        "edge_label_vocab": edge_label_index,
        "category_vocab": category_index,
    }
