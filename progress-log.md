# Progress Log

- 2026-04-16 23:15 CDT
  Added ranker labeling workflow and filled the first-pass review labels.
  Notes: Implemented `label-ranker-results`, generated `artifacts/ranker-compare/ranker-labels.jsonl`, and applied an initial `better` / `worse` / `unclear` pass for manual review.

- 2026-04-16 23:05 CDT
  Added heuristic-vs-GraphCodeBERT comparison tool.
  Notes: Contributors can now run `compare-rankers` to compare both ranking modes on the same repo and diff and inspect promotions, drops, and overlap.

- 2026-04-16 23:00 CDT
  Note for Yash.
  Notes: Please read `docs/MODEL_SETUP.md` first, then manually review `artifacts/ranker-compare/ranker-labels.jsonl`. The current next step is manual checking of promoted and dropped findings before any fine-tuning work starts.

- 2026-04-16 17:35 CDT
  Integrated GraphCodeBERT into the offline scorer ranker.
  Notes: Added deterministic candidate serialization, GraphCodeBERT-based scoring, blended ranking with heuristics, and automatic heuristic fallback when the model is unavailable.

- 2026-04-16 17:30 CDT
  Verified GraphCodeBERT ranker integration.
  Notes: Focused backend checks passed with `ruff` and `pytest`; scorer tests now cover heuristic fallback, deterministic serialization, and model-backed ranking selection.

- 2026-04-16 17:10 CDT
  Installed and loaded `microsoft/graphcodebert-base` locally.
  Notes: Model download completed successfully; local environment can now use GraphCodeBERT for inference.

- 2026-04-16 16:55 CDT
  Updated `idea.txt` to reflect the new MVP.
  Notes: Reframed the product around AST, ASG, CPG, cross-language stitching, invariant scoring, GraphCodeBERT ranking, Gemma reasoning, and deterministic verification.

- 2026-04-16 16:40 CDT
  Implemented offline CPG invariant scorer pipeline.
  Notes: Added stitcher, invariant specs, path miner, ranker, hosted reasoner abstraction, deterministic verifier, scorer CLI, replay flow, and artifact outputs such as `violations.json` and training-example JSONL files.

- 2026-04-16 16:25 CDT
  Added cross-language stitcher and stitcher coverage metrics.
  Notes: The graph now links frontend HTTP calls, FastAPI routes, Supabase entities, migrations, RLS policies, and Celery task relationships. Run summaries now report stitcher coverage health.

- 2026-04-16 16:10 CDT
  Extended the fused CPG schema.
  Notes: Added node and edge types for routes, HTTP client calls, database entities, migrations, RLS policies, and task relationships to support business-logic analysis.

- 2026-04-16 15:50 CDT
  Implemented Code Property Graph pipeline.
  Notes: Added repository indexing, AST fusion, ASG fusion, CPG build/export, diff support, PyG conversion, CLI commands, docs, and tests.

- 2026-04-16 15:30 CDT
  Added ASG builder script.
  Notes: Introduced semantic graph generation for modules, symbols, imports, and semantic edges. CLI can emit JSON and summary output for the repository.

- 2026-04-16 15:10 CDT
  Added AST builder script.
  Notes: Added repo AST generation CLI and summary mode. Later improved it to expose parser availability and source-file counts more clearly.

- 2026-04-16 14:50 CDT
  Added AST tree/graph support toward the frontend repo view.
  Notes: Backend AST endpoints and frontend AST panel work were started, including a Cytoscape-based graph direction and build trigger flow.

- 2026-04-16 14:30 CDT
  Improved Supabase schema error handling in the backend.
  Notes: Missing-table errors such as `public.organization_members` are now treated more clearly as schema/migration problems instead of opaque FastAPI failures.

- 2026-04-16 14:10 CDT
  Documented app architecture and pipeline.
  Notes: Added dedicated architecture and pipeline documentation under `docs/` so contributors can understand the frontend, backend, Supabase, worker, and analysis flows.
