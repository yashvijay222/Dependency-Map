# Dependency Map Pipeline

This document explains the runtime pipeline used by the app, from user requests and GitHub events through graph building, scoring, persistence, and feedback-driven refinement.

## Pipeline Goals

The pipeline is designed to answer four core questions:

- what changed in a repository?
- what internal files are likely affected?
- what other repositories may be affected?
- how should the scoring improve over time as teams give feedback?

## Pipeline Modes

The system can be triggered in two broad ways:

- on-demand through API requests
- event-driven through GitHub webhooks and scheduled workers

## End-to-End Flows

### Flow A: Dashboard and basic tenancy lookup

This is the simplest path and the first one most developers hit locally.

1. The frontend loads the signed-in user from Supabase.
2. It calls `GET /v1/dashboard`.
3. FastAPI verifies the JWT.
4. The backend queries `organization_members` for the current user.
5. The backend loads matching `organizations`.
6. The response is returned to the UI.

This path is small, but it validates auth, organization membership, API connectivity, and database readiness.

### Flow B: Manual PR or commit analysis

Entry point: [backend/app/routers/analyses.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/routers/analyses.py)

1. A client calls `POST /v1/repos/{repo_id}/analyze`.
2. The backend validates the caller and org membership.
3. The request inserts a `pr_analyses` row with status `pending`.
4. The request schedules `run_analysis_job`.
5. The worker marks the analysis as `running`.
6. The worker gathers repository, organization, and GitHub installation metadata.
7. The worker downloads base and head tarballs for the commit range.
8. The worker builds dependency graphs for both versions.
9. The worker computes changed files from the GitHub compare API.
10. The worker runs scoring and blast-radius logic.
11. The worker may compute cross-repo impact.
12. The worker persists summaries and derived artifacts.
13. The analysis row is marked `completed` or `failed`.

### Flow C: Webhook-driven repository refresh

Entry point: [backend/app/routers/webhooks.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/routers/webhooks.py)

Supported GitHub event patterns include:

- `pull_request`
- `push`
- `create`
- `delete`
- `installation`

Behavior by event:

- `pull_request`
  Creates a `pr_analyses` row and schedules analysis.

- `push`
  Snapshots the pushed branch, then either rebuilds the org graph or computes drift depending on whether the pushed branch is the repo default branch.

- `create` for a branch
  Creates a first snapshot for that branch.

- `delete` for a branch
  Removes persisted branch-specific rows and refreshes dependent graph state.

### Flow D: Scheduled refresh and training

Entry point: [backend/app/celery_app.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/celery_app.py)

With Celery Beat enabled, the system can:

- enqueue snapshots for all organizations every six hours
- run drift checks every twelve hours
- backfill analysis schema versions weekly
- train org models nightly

This keeps graph state and learned artifacts fresh even without direct user interaction.

## Core Stages

### Stage 1: Intake and authorization

Whether the trigger is an API request or a webhook, the system first determines:

- who is calling
- what organization or repo the action targets
- whether the action is allowed

For user-authenticated API calls, this means checking Supabase JWTs and membership in `organization_members`.

### Stage 2: Source acquisition

For analysis and snapshot jobs, the system needs source code content. It gets this by:

- resolving the GitHub App installation for the org
- requesting an installation token
- downloading a tarball for the target repo and commit SHA

The tarball is extracted into a temporary directory and used as the input to graph and AST stages.

### Stage 3: Dependency graph construction

Entry point: [backend/app/services/graph_builder.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/services/graph_builder.py)

The graph builder currently focuses on TS/JS source files and package edges.

It:

- walks source files under the checked-out repo snapshot
- skips generated and irrelevant directories like `node_modules`, `.next`, and `dist`
- parses import/export/require/dynamic import statements
- uses tree-sitter when available
- falls back to regex extraction when needed
- resolves relative imports to repository files
- records external package references as `package:*` nodes

Outputs:

- graph nodes representing files
- graph edges representing file imports and manifest/package dependencies

This graph is the base structure used by blast-radius and cross-repo computations.

### Stage 4: Diff and changed-file acquisition

For PR and commit analysis, the worker compares the base and head commits using GitHub APIs.

Important outputs:

- changed file list
- graph edge additions and removals between base and head

These are fed into scoring and risk computation.

### Stage 5: Blast-radius scoring

Entry point: [backend/app/services/blast_radius.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/services/blast_radius.py)

The local blast-radius algorithm uses reverse traversal:

- treat each changed file as a seed
- walk backwards through importers
- assign greater weight to nodes closer to the seed
- produce an impact score and impacted module list

Outputs include:

- `impacted_modules`
- `blast_radius_score`
- `confidence`
- `risks`
- `changed_dependency_edges`

This stage is the main heuristic explanation layer for local repository change impact.

### Stage 6: Intelligent scoring and optional ML enrichment

Entry point: [backend/app/services/intelligent_scorer.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/services/intelligent_scorer.py)

The scorer chooses between:

- graph-based heuristic fallback
- GNN-backed inference when a valid org model is present

It also attempts to:

- build AST graphs
- embed AST nodes
- attach ML metadata to analysis summaries

Returned fields may include:

- `ml_metadata`
- `schema_version`
- `changed_nodes`
- `risk_anomalies`

Fallback behavior matters here. If no usable model exists, the app still produces a valid analysis using deterministic graph logic.

### Stage 7: Cross-repo graph resolution

Entry point: [backend/app/worker/cross_repo_tasks.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/worker/cross_repo_tasks.py)

Cross-repo analysis builds on branch snapshots and package metadata.

The process is:

1. snapshot a repo branch
2. extract published/workspace packages
3. save package metadata to `repo_packages`
4. load latest org snapshots
5. build a package registry
6. resolve repo-to-repo edges
7. persist those edges to staging
8. swap staging into the live `cross_repo_edges` table

This gives the system an organization-wide dependency map rather than isolated per-repo graphs.

### Stage 8: Cross-repo blast radius

When an analysis requests cross-repo impact or when inbound consumer edges exist, the pipeline:

- loads cross-repo consumer edges for the changed repo
- loads consumer repository graphs
- creates a namespaced super-graph
- bridges consumer file importers into the changed repository anchor
- performs reverse traversal on that super-graph

Outputs include:

- `cross_repo_impacts`
- `aggregate_cross_repo_score`
- `cross_repo_truncated`

These are also used to populate `risk_hotspots` in affected consumer repos.

### Stage 9: Branch snapshot and drift monitoring

Entry points:

- [backend/app/routers/branches.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/routers/branches.py)
- [backend/app/worker/cross_repo_tasks.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/worker/cross_repo_tasks.py)

Branch snapshots persist:

- `dependency_snapshots`
- `repo_packages`
- `dependency_edges`

Branch drift compares two branch snapshots and stores:

- overlap score
- drift type
- conflicting file set
- drift signal JSON

It also creates `risk_hotspots` tagged with reason `branch_drift`.

This is the basis for “see how branches diverge as work progresses.”

### Stage 10: Persistence

The pipeline writes to several artifact tables depending on the job:

- `pr_analyses`
- `dependency_snapshots`
- `dependency_edges`
- `repo_packages`
- `cross_repo_edges`
- `branch_drift_signals`
- `risk_hotspots`
- `review_feedback`
- `model_artifacts`

The exact set depends on whether the job is:

- PR analysis
- branch snapshot
- drift computation
- cross-repo rebuild
- feedback update
- ML training

### Stage 11: Feedback loop

Entry point: [backend/app/services/feedback_engine.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/services/feedback_engine.py)

Users can submit feedback about comments or findings. The feedback engine:

- records review actions in `review_feedback`
- aggregates positive and negative outcomes
- derives org-specific edge-type weights
- adjusts attention threshold and decay factor
- stores the learned weights in `model_artifacts`

This is an RLHF-style refinement loop scoped to each organization.

### Stage 12: Nightly model training

Entry point: [backend/app/worker/ml_tasks.py](/c:/Users/aroud/OneDrive/Documents/GitHub/Website/Dependency-Map/backend/app/worker/ml_tasks.py)

The nightly ML pipeline:

1. loads the latest AST graphs for repos in the org
2. trains a GAT + GraphSAGE link prediction model
3. stores the model artifact in `model_artifacts`
4. updates org scoring weights from accumulated feedback

This makes the system progressively more organization-specific over time.

## Offline CPG contract scorer (optional Celery bridge)

The hosted pipeline above uses TS/JS dependency graphs and GNN scoring. Separately, the **offline CPG invariant scorer** in `backend/cpg_builder/` can run on a materialized repository directory (same layout as a tarball extract).

- **Celery task** `dm.run_cpg_contract_score` (see [backend/app/celery_app.py](backend/app/celery_app.py)) invokes [backend/app/worker/cpg_contract_tasks.py](backend/app/worker/cpg_contract_tasks.py), which wraps `score_repository` with `(repo_root, out_dir, base, head)`.
- Use this when a worker already has a checkout: pass absolute paths for `repo_root` and `out_dir`. Persisting `violations.json` / `verifier_audit.json` to Supabase or object storage is a product follow-up.
- **Ranker review metrics:** `uv run python scripts/aggregate_ranker_labels.py path/to/ranker-labels.jsonl` prints `net_improvement`, `review_precision`, and `unclear_rate` for Phase 0 evaluation.

## Persistence Matrix

### PR analysis writes

- `pr_analyses`
- `dependency_edges`
- `risk_hotspots`
- optionally derived cross-repo hotspot rows

### Branch snapshot writes

- `dependency_snapshots`
- `repo_packages`
- `dependency_edges`

### Org graph rebuild writes

- `cross_repo_edges_staging`
- `cross_repo_edges` through the swap RPC

### Drift computation writes

- `branch_drift_signals`
- `risk_hotspots`

### Feedback and ML writes

- `review_feedback`
- `model_artifacts`

## Degradation and Fallbacks

The pipeline is designed to stay useful even when some capabilities are missing.

Examples:

- no Celery: execute inline or through FastAPI background tasks
- no GitHub App credentials: produce stub summaries instead of full graph-backed analyses
- no trained model: use uniform blast-radius fallback
- no AST graph or embeddings: keep schema version lower and omit ML-enriched fields

This keeps development workflows moving while advanced capabilities are still being configured.

## Failure Modes to Expect

Common operational failure classes:

- missing Supabase migrations
- missing GitHub installation for a repo’s org
- invalid or absent webhook secret
- missing Redis when `USE_CELERY=true`
- analysis rows that cannot find corresponding repositories
- partial ML dependencies in environments that only installed the base backend extras

The fastest first checks are usually:

1. confirm `.env` points to the intended Supabase project
2. confirm all `supabase/migrations` files were applied
3. confirm the repository is registered in `repositories`
4. confirm the org has a `github_installations` row
5. confirm workers are running if async jobs are expected

## Mental Model for Maintainers

A good way to think about the app is:

- the frontend is a thin authenticated operator console
- FastAPI is the orchestration and policy layer
- Supabase is the system of record
- GitHub is the source-of-truth for repo contents and change events
- Celery is the execution engine for long-running work
- the graph, feedback, and ML layers progressively enrich a base dependency model

That mental model makes the codebase much easier to navigate.
