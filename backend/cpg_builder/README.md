# CPG Builder

`cpg_builder` constructs a fused Code Property Graph for a local repository by combining:

- repository structure and file metadata
- Tree-sitter AST structure
- an extensible semantic layer with scopes, declarations, references, imports, callsites, and def-use links

The graph is emitted as a directed, edge-labeled, attributed multigraph and is suitable for export to JSON, GraphML, NDJSON, and a **PyG-friendly JSON pack** (`--format pyg_json`) for `torch_geometric` loaders.

## Highlights

- Stable node and edge IDs derived from relative paths and anchor spans
- Repository, syntax, and semantic nodes fused into one `networkx.MultiDiGraph`
- Incremental AST rebuild support through Tree-sitter previous-tree reuse
- Git-aware diff mode that reports graph additions, removals, and changed attributes
- `pyg_json` export with `edge_index`, per-node label codes, and stable `node_id` ordering for PyG loaders

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

Export PyTorch Geometric–friendly JSON (`edge_index`, `x`, `node_ids`):

```bash
python -m cpg_builder.main build --repo /path/to/repo --format pyg_json --out out/cpg_pyg.json
```

Diff two revisions:

```bash
python -m cpg_builder.main diff --repo /path/to/repo --base main --head HEAD --out out/diff.json
```

Run the offline invariant scorer:

```bash
python -m cpg_builder.main score --repo /path/to/repo --out-dir out/offline-score --base main --head HEAD
```

Replay queued hosted-reasoner work:

```bash
python -m cpg_builder.main replay --queue out/offline-score/reasoner_queue.jsonl --out-dir out/offline-score-replay
```

Replay with deterministic re-verification (requires the same CPG JSON as the scored run, and queue rows that include `candidate_path`):

```bash
python -m cpg_builder.main replay \
  --queue out/offline-score/reasoner_queue.jsonl \
  --out-dir out/replay-verify \
  --cpg-json out/cpg.json \
  --re-verify
```

Split accumulated reasoner training JSONL (from `CPG_REASONER_TRAINING_JSONL` or `--training-jsonl` on replay):

```bash
python -m cpg_builder.main prepare-reasoner-dataset --input training.jsonl --out-dir out/reasoner-dataset
```

Compare heuristic and GraphCodeBERT ranking on the same analysis run:

```bash
python -m cpg_builder.main compare-rankers --repo /path/to/repo --out-dir out/ranker-compare --base main --head HEAD
```

Generate a JSONL labeling file from the comparison output:

```bash
python -m cpg_builder.main label-ranker-results --compare-dir out/ranker-compare --out out/ranker-labels.jsonl
```

Prepare a reviewed GraphCodeBERT fine-tuning dataset:

```bash
python -m cpg_builder.main prepare-graphcodebert-dataset --labels out/ranker-labels.jsonl --out-dir out/graphcodebert-dataset
```

## Hosted reasoner (OpenAI-compatible or Gemini)

Set `CPG_REASONER_PROVIDER` to `stub` (default deterministic rules), `openai` (Chat Completions JSON), or `gemini` / `google` (Generative Language API with `responseMimeType: application/json`). Model responses are validated for required keys before the deterministic verifier runs.

| Variable | Purpose |
|----------|---------|
| `CPG_REASONER_PROVIDER` | `stub`, `openai`, `gemini`, `google`, `gemma` (alias of Gemini API) |
| `CPG_REASONER_OPENAI_API_KEY` | API key (falls back to `OPENAI_API_KEY`) |
| `CPG_REASONER_OPENAI_BASE_URL` | Default `https://api.openai.com/v1` |
| `CPG_REASONER_OPENAI_MODEL` | Default `gpt-4o-mini` |
| `CPG_REASONER_GEMINI_API_KEY` | Google AI Studio key |
| `CPG_REASONER_GEMINI_MODEL` | Default `gemini-2.0-flash` (pick a Gemma/Gemini id your key supports) |
| `CPG_REASONER_HTTP_TIMEOUT_SEC` | HTTP timeout (default 120) |
| `CPG_REASONER_TRAINING_JSONL` | Append-only log of `{evidence_pack, reasoner_output, provider}` for Phase 2 datasets |

Fine-tuned GraphCodeBERT: set `CPG_GRAPHCODEBERT_LOCAL_DIR` to a directory produced by `scripts/train_graphcodebert.py` (Hugging Face `from_pretrained` layout).

## Stitcher limits

`stitcher.py` links FastAPI routes, frontend `fetch`/`apiFetchOptional` calls, Supabase `.table`/`.rpc` usage parsed from Python handlers, migration-defined entities and `CREATE POLICY` rows, and Celery `send_task` / `.delay` patterns. Coverage is **regex and decorator-driven**, not a full multi-language semantic resolver: dynamic route strings, indirect task names, or framework-specific HTTP clients may be missed. See `StitcherMetrics` (`low_stitcher_coverage`, `missing_seam_categories`) in scorer output for gating.

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
