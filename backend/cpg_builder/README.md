# CPG Builder

`cpg_builder` constructs a fused Code Property Graph for a local repository by combining:

- repository structure and file metadata
- Tree-sitter AST structure
- an extensible semantic layer with scopes, declarations, references, imports, callsites, and def-use links

The graph is emitted as a directed, edge-labeled, attributed multigraph and is suitable for export to JSON, GraphML, NDJSON, and tensorized downstream training pipelines.

## Highlights

- Stable node and edge IDs derived from relative paths and anchor spans
- Repository, syntax, and semantic nodes fused into one `networkx.MultiDiGraph`
- Incremental AST rebuild support through Tree-sitter previous-tree reuse
- Git-aware diff mode that reports graph additions, removals, and changed attributes
- PyTorch Geometric conversion helper for `x`, `edge_index`, `edge_type`, and `node_type`

## CLI

Build a whole-repo graph:

```bash
python -m cpg_builder.main build --repo /path/to/repo --out out/cpg.json
```

Build a single-file graph:

```bash
python -m cpg_builder.main build --repo /path/to/repo --file src/app.ts --out out/app-cpg.json
```

Export GraphML:

```bash
python -m cpg_builder.main build --repo /path/to/repo --format graphml --out out/cpg.graphml
```

Diff two revisions:

```bash
python -m cpg_builder.main diff --repo /path/to/repo --base main --head HEAD --out out/diff.json
```

## Schema

Every node has:

- `id`
- `label`
- `category`
- `language`
- `file_path` when applicable

Every edge has:

- `id`
- `label`
- `src`
- `dst`
- `category`

See [../../docs/CPG_ARCHITECTURE.md](../../docs/CPG_ARCHITECTURE.md) for the detailed schema and layering model.
