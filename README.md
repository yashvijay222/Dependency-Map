# Dependency Map

**Pre-merge contract verification** across your stack (routes, schema, async boundaries)—Dependency Map turns graph-aware analysis into reviewable findings before code ships.

Monorepo for the Dependency Map OS MVP: **Next.js** (`frontend/`), **FastAPI** (`backend/`), and **Supabase** (SQL in `supabase/migrations`).

## Documentation

- [Operations / staging matrix](docs/OPS_ENVIRONMENTS.md)
- [Architecture guide](docs/ARCHITECTURE.md)
- [Pipeline guide](docs/PIPELINE.md)
- [Local model setup guide](docs/MODEL_SETUP.md)
- [Reviewer metric guide](docs/REVIEWER_METRIC.md)
- [Internal SLO targets](docs/SLO.md)
- [Security review checklist](docs/SECURITY_REVIEW.md)
- [Demo repo checklist](docs/DEMO_REPO.md)
- [Case study template](docs/CASE_STUDY_TEMPLATE.md)

## Utilities

- Build an AST graph for the current repo: `cd backend && uv run python scripts/build_ast.py .. --output ../artifacts/repo-ast.json`
- Build an ASG for the current repo: `cd backend && uv run python scripts/build_asg.py .. --output ../artifacts/repo-asg.json`
- Build a fused CPG for the current repo: `cd backend && uv run python -m cpg_builder.main build --repo .. --out ../artifacts/repo-cpg.json`
- Diff two revisions as a graph diff: `cd backend && uv run python -m cpg_builder.main diff --repo .. --base main --head HEAD --out ../artifacts/repo-cpg-diff.json`
- Run the offline invariant scorer: `cd backend && uv run python -m cpg_builder.main score --repo .. --out-dir ../artifacts/offline-score --base main --head HEAD`
- Replay queued hosted-reasoner work: `cd backend && uv run python -m cpg_builder.main replay --queue ../artifacts/offline-score/reasoner_queue.jsonl --out-dir ../artifacts/offline-score-replay`
- Compare heuristic and GraphCodeBERT ranking side by side: `cd backend && uv run python -m cpg_builder.main compare-rankers --repo .. --out-dir ../artifacts/ranker-compare --base main --head HEAD`
- Generate a labeling file from the ranker comparison output: `cd backend && uv run python -m cpg_builder.main label-ranker-results --compare-dir ../artifacts/ranker-compare --out ../artifacts/ranker-compare/ranker-labels.jsonl`
- Prepare a reviewed GraphCodeBERT fine-tuning dataset: `cd backend && uv run python -m cpg_builder.main prepare-graphcodebert-dataset --labels ../artifacts/ranker-compare/ranker-labels.jsonl --out-dir ../artifacts/graphcodebert-dataset`
- Fine-tune a GraphCodeBERT classification head on the prepared dataset: `cd backend && uv run --active python scripts/train_graphcodebert.py --train ../artifacts/graphcodebert-dataset/graphcodebert-train.jsonl --val ../artifacts/graphcodebert-dataset/graphcodebert-val.jsonl --out-dir ../artifacts/graphcodebert-model`
- Aggregate ranker label metrics (`net_improvement`, `review_precision`, `unclear_rate`): `cd backend && uv run python scripts/aggregate_ranker_labels.py ../artifacts/ranker-compare/ranker-labels.jsonl`
- Split reasoner training JSONL for fine-tuning: `cd backend && uv run python -m cpg_builder.main prepare-reasoner-dataset --input ../artifacts/reasoner-training.jsonl --out-dir ../artifacts/reasoner-dataset`
- Export CPG as PyG-friendly JSON: `cd backend && uv run python -m cpg_builder.main build --repo .. --format pyg_json --out ../artifacts/repo-cpg-pyg.json`

## CPG pipeline

The production CPG pipeline lives in [backend/cpg_builder/README.md](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/cpg_builder/README.md) and the architecture note lives in [docs/CPG_ARCHITECTURE.md](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/docs/CPG_ARCHITECTURE.md).

## Prerequisites

- Node 20+
- [uv](https://docs.astral.sh/uv/) (Python 3.11+)
- A Supabase project (Auth + Postgres)
- Optional: [Docker](https://docs.docker.com/get-docker/) (Redis, API, Celery workers, and Beat via Compose)
- Optional: [Supabase CLI](https://supabase.com/docs/guides/cli) for applying migrations from the repo

## Setup guide

### 1. Clone and install dependencies

From the repository root:

```bash
git clone <your-fork-or-repo-url>
cd Dependency-Map
npm install
```

Install the frontend workspace packages (workspace is `frontend/`):

```bash
npm install -w frontend
```

Install the Python API and dev tools:

```bash
cd backend
uv sync --extra dev
```

Optional ML stack (PyTorch Geometric, GNN training, CodeBERT fallback). Use this if you run GNN training or want the full test suite including PyG-backed tests:

```bash
cd backend
uv sync --extra dev --extra ml
```

### 2. Environment variables

All variables are documented in **`.env.example`** at the repo root. Copy it and fill in your values:

```bash
cp .env.example .env
```

- **Frontend:** `NEXT_PUBLIC_*` variables must be available to Next.js. **`frontend/next.config.ts` loads the repo root `.env`** via `loadEnvConfig`, so a single root `.env` with the Frontend block is enough. You can also use **`frontend/.env.local`** for overrides. Use the **anon** key only in the browser; never the service role.
- **Backend:** FastAPI loads **`../.env`** (repo root) then **`backend/.env`** (see `backend/app/config.py`). A single **root `.env`** containing both Frontend and Backend blocks is usually sufficient. For server-only overrides, use **`backend/.env`**.

Add any optional keys your deployment needs (for example `OPENAI_API_KEY` for embeddings and hybrid search, if you use those features).

### 3. Supabase database

1. Create a project in the [Supabase dashboard](https://supabase.com/dashboard).
2. Enable extensions and run migrations in order:
   - Use the Supabase SQL editor, **or**
   - `supabase link` then `supabase db push` if you use the CLI.
3. Apply all files under `supabase/migrations/` in filename (timestamp) order.

This provisions tables, RLS policies, `pgvector` (where defined), and RPCs used by the API.

If the API returns a PostgREST error like `PGRST205` or says `public.organization_members` is missing from the schema cache, the migrations have not been applied to the connected Supabase project yet.

### 4. GitHub App (optional)

For repository analysis, webhooks, and tarball fetch, create a [GitHub App](https://docs.github.com/en/apps/creating-github-apps) and set `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, and `GITHUB_WEBHOOK_SECRET` in `.env`. You can leave these empty for UI-only local development against Supabase Auth.

### 5. Redis and Celery (optional for full pipeline)

- **Local Redis:** install Redis and point `REDIS_URL` at it (for example `redis://localhost:6379/0`), or use Docker only for Redis: `docker compose up -d redis`.
- Set **`USE_CELERY=true`** when you run the API with a Celery worker (see [Startup guide](#startup-guide)).

---

## Startup guide

### Option A: Local development (API + Next.js, no Docker for the app)

**Terminal 1 — Backend**

```bash
cd backend
uv sync --extra dev
# --reload-dir app avoids watching .venv (otherwise uv sync / IDE triggers endless reloads)
uv run uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
```

With Celery locally: start Redis, set `USE_CELERY=true` in `.env`, then run workers (analysis jobs route to **`cpg_heavy`**):

```bash
cd backend
uv run celery -A app.celery_app:celery_app worker -l info -Q celery,snapshot
uv run celery -A app.celery_app:celery_app worker -l info -Q cpg_heavy --concurrency=2
```

For ML training tasks and Beat schedules, also run workers for the `ml` queue and Celery Beat (see Option B commands).

**Terminal 2 — Frontend**

```bash
npm install
cd frontend && npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Protected routes include `/dashboard`, `/orgs/...`, and `/repos/...`.

**If the Next.js build fails with odd errors (for example missing `/_document`):** delete `frontend/.next` and run `npm run build -w frontend` again. On Windows, syncing the repo under OneDrive can occasionally interfere with the Next cache; moving the clone outside synced folders can help.

### Option B: Docker Compose (API + Redis + workers + Beat)

From the **repo root** (where `docker-compose.yml` lives), ensure `.env` exists and includes at least Supabase and app settings from `.env.example`.

```bash
docker compose up --build
```

This starts:

- **redis** — broker/backend for Celery
- **api** — FastAPI on port **8000** (`USE_CELERY=true`, `REDIS_URL` points at the Compose Redis service)
- **worker** — Celery worker for `celery` and `snapshot` queues
- **worker-cpg** — dedicated worker for `cpg_heavy` (PR graph analysis) with concurrency cap **2**
- **worker-ml** — Celery worker for the `ml` queue (training jobs)
- **beat** — Celery Beat for scheduled tasks

Point `NEXT_PUBLIC_API_URL` at `http://127.0.0.1:8000` and run the frontend locally as in Option A, or add a frontend service later if you containerize it.

### Quick reference

| Service        | Default URL / port        |
|----------------|---------------------------|
| Next.js (dev)  | http://localhost:3000     |
| FastAPI        | http://127.0.0.1:8000     |
| Redis (Compose)| localhost:6379            |

---

## Environment (reference)

See **`.env.example`** for the full list. Summary:

- **Frontend:** `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SITE_URL`
- **Backend:** `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `CORS_ORIGINS`, `REDIS_URL`, `USE_CELERY`, GitHub App vars, `API_KEY_PEPPER`

Apply migrations in the Supabase SQL editor or via `supabase db push` when using the Supabase CLI.

## Ranker evaluation (one command)

From the repo root (see [docs/REVIEWER_METRIC.md](docs/REVIEWER_METRIC.md) for the full checklist):

```bash
npm run ranker:eval
```

This runs `compare-rankers` on `--repo ..` with `--base main` and `--head HEAD`, generates `ranker-labels.jsonl` via `label-ranker-results`, then prints aggregate label metrics. Edit `review_label` in the JSONL before trusting metrics; override refs by running the underlying commands from [docs/MODEL_SETUP.md](docs/MODEL_SETUP.md) instead.

## CI

From the repo root: `npm install`, `npm run lint`, `npm run build` (web); `cd backend && uv sync --extra dev && uv run ruff check app` (API).
