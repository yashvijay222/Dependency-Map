# Local Model Setup

This guide helps contributors set up the local GraphCodeBERT ranker used by the offline CPG scorer.

## What This Enables

After setup, contributors can:

- run the offline scorer with GraphCodeBERT-backed ranking
- compare heuristic ranking versus GraphCodeBERT ranking
- generate labeling files for future GraphCodeBERT fine-tuning

GraphCodeBERT is currently the local ranking model in the pipeline. It is not the final verifier and it does not replace deterministic checks.

## Model Used

- Hugging Face model: `microsoft/graphcodebert-base`

This is the base pretrained checkpoint. It is used for inference right now, not task-specific fine-tuning.

## Prerequisites

- Python 3.11+
- `uv`
- enough disk space for model weights and Hugging Face cache
- internet access for the first model download

Optional:

- `HF_TOKEN` for higher Hugging Face rate limits

## Recommended Environment

Use the backend project environment, not the repo-root `venv`.

From the repo root:

```powershell
cd backend
uv sync --extra dev
```

If contributors also want the optional ML stack:

```powershell
cd backend
uv sync --extra dev --extra ml
```

## Install Model Dependencies

These packages are already declared in `backend/pyproject.toml`, so in most cases `uv sync` is enough.

If you need to add them explicitly in an active environment:

```powershell
cd backend
uv add --active transformers torch sentencepiece huggingface_hub
```

## Download And Test GraphCodeBERT

Run:

```powershell
cd backend
uv run --active python -c "from transformers import AutoTokenizer, AutoModel; t=AutoTokenizer.from_pretrained('microsoft/graphcodebert-base'); m=AutoModel.from_pretrained('microsoft/graphcodebert-base'); print('ok', t.__class__.__name__, m.__class__.__name__)"
```

Expected success signal:

```text
ok RobertaTokenizer RobertaModel
```

## Common Warnings

These warnings are expected and usually safe:

- `HF_TOKEN` warning
  Notes: optional; the model is public

- Hugging Face symlink warning on Windows
  Notes: caching still works, but may use more disk space

- `UNEXPECTED` / `MISSING` model keys when loading
  Notes: expected when loading the base checkpoint into `AutoModel`; this is not a task-specific classifier head yet

## Environment Variables

The ranker behavior is controlled with:

```powershell
$env:CPG_RANKER_BACKEND="graphcodebert"
```

Fallback to heuristics only:

```powershell
$env:CPG_RANKER_BACKEND="heuristic"
```

Optional overrides:

```powershell
$env:CPG_GRAPHCODEBERT_MODEL="microsoft/graphcodebert-base"
$env:CPG_GRAPHCODEBERT_MAX_LENGTH="512"
```

## Run The Scorer With GraphCodeBERT

```powershell
cd backend
$env:CPG_RANKER_BACKEND="graphcodebert"
uv run --active python -m cpg_builder.main score --repo .. --out-dir ../artifacts/offline-score --base main --head HEAD
```

Artifacts to inspect:

- `artifacts/offline-score/violations.json`
- `artifacts/offline-score/verifier_audit.json`
- `artifacts/offline-score/ranker_examples.jsonl`

## Compare Heuristic Vs GraphCodeBERT Ranking

```powershell
cd backend
uv run --active python -m cpg_builder.main compare-rankers --repo .. --out-dir ../artifacts/ranker-compare --base main --head HEAD
```

Comparison outputs:

- `artifacts/ranker-compare/ranker-comparison.json`
- `artifacts/ranker-compare/ranker-comparison.md`

## Generate A Labeling File

```powershell
cd backend
uv run --active python -m cpg_builder.main label-ranker-results --compare-dir ../artifacts/ranker-compare --out ../artifacts/ranker-compare/ranker-labels.jsonl
```

This creates a JSONL file that contributors can review and label for future ranker fine-tuning.

## Troubleshooting

### `uv` cache permission error on Windows

Example:

```text
Failed to initialize cache at C:\Users\<user>\AppData\Local\uv\cache
```

What to try:

- rerun with `uv run --active ...`
- make sure the backend environment is the one being used
- clear/fix permissions on the local `uv` cache
- if you are in a managed shell, rerun with elevated permissions if needed

### Model loads but scoring is still heuristic-only

Check:

- `CPG_RANKER_BACKEND` is set to `graphcodebert`
- the model downloaded successfully
- the scorer output contains `rank_phase: phase0_graphcodebert_blend`

### PowerShell line break issue with `--head`

Use the command on one line:

```powershell
uv run --active python -m cpg_builder.main score --repo .. --out-dir ../artifacts/offline-score --base main --head HEAD
```

## Contributor Workflow

Recommended contributor flow:

1. Set up the backend environment.
2. Download and test GraphCodeBERT locally.
3. Run `score` with GraphCodeBERT enabled.
4. Run `compare-rankers`.
5. Run `label-ranker-results`.
6. Review and label the generated JSONL file.

## Current Role Of GraphCodeBERT In The Project

GraphCodeBERT currently fits into the pipeline here:

`AST -> ASG -> CPG -> stitcher -> path miner -> GraphCodeBERT ranker -> Gemma reasoner -> deterministic verifier`

Its job is to improve candidate ordering before long-context reasoning. The verifier remains the final trust boundary.
