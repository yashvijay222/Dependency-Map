# Dependency Map OS

## Current Idea

Dependency Map OS is no longer just a dependency graph product.

It is a graph-driven architecture and business-logic verification system for modern codebases. The system builds structural and semantic representations of a repository, stitches them across application boundaries, mines risky change paths, ranks those paths, reasons over the strongest candidates, and only surfaces findings that survive deterministic verification.

The core product question is:

> Given a change, what business or architectural contract is now at risk, and can we verify that risk before developers merge or deploy it?

## What The Product Analyzes

- Frontend to backend API seams
- Backend to database schema seams
- Migration and branch-state mismatches
- Auth and RLS protection boundaries
- Async worker and queue contracts
- Repository and branch blast radius

## Graph Stack

### 1. AST

- Syntax-preserving structure
- Tree-sitter-backed parsing
- Stable anchors for code findings

### 2. ASG

- Semantic structure
- Declarations, references, imports, scopes, calls, def-use

### 3. CPG

- Fused repository + AST + ASG multigraph
- Exportable to JSON, GraphML, and PyG-oriented formats

### 4. Cross-Language Stitcher

- Frontend HTTP calls -> FastAPI routes
- FastAPI routes -> Supabase tables and RPCs
- Routes -> RLS policies
- Celery producers -> task consumers

### 5. Diff-Aware Invariant Scorer

- Graph diff between base and head
- Invariant-driven seed selection
- Candidate witness path mining
- Ranking, reasoning, and deterministic verification

## Current Analysis Pipeline

`Repository -> AST -> ASG -> CPG -> stitcher -> graph diff -> invariant compiler -> path miner -> GraphCodeBERT ranker -> Gemma reasoner -> deterministic verifier -> developer output`

## What Each Stage Does

- AST tells the system what the code looks like syntactically.
- ASG tells the system what the code means semantically.
- CPG gives one fused graph substrate for downstream analysis.
- The stitcher connects frontend, backend, schema, RLS, and worker seams.
- The path miner turns graph changes into concrete candidate breakage paths.
- GraphCodeBERT ranks which candidate paths are most suspicious.
- Gemma explains and structures those candidate findings.
- The verifier decides what is safe to show developers.

## Model Architecture

### GraphCodeBERT

- Local ranking model
- Used before long-context reasoning
- Ranks candidate witness paths and helps reduce token cost downstream
- Now integrated into the scorer as a blended ranker with heuristic fallback

### Gemma

- Long-context reasoning layer
- Consumes evidence packs from the best-ranked candidates
- Produces structured JSON hypotheses and explanations
- Not the trust boundary

### Deterministic Verifier

- Final trust boundary
- Confirms, partially confirms, or rejects findings
- Checks branch-aware schema existence, route/task presence, RLS coverage, and edge confidence

## Why This Architecture Matters

The hard bugs in this repo are not single-file syntax bugs. They are cross-system contract failures such as:

- Frontend calling a stale or mismatched backend route
- Backend referencing a table removed or absent in the analyzed branch
- A route appearing unguarded even though protection lives in RLS
- A Celery producer assuming a consumer or payload contract that no longer exists

This means the product has to reason across multiple files, multiple languages, and multiple system layers at once.

## What Exists Now

- AST build CLI
- ASG build CLI
- Fused CPG build CLI
- Graph diff CLI
- Offline invariant scorer
- Cross-language stitcher
- Invariant specifications
- Deterministic evidence packing
- Hosted reasoner abstraction with replay queue
- Deterministic verifier
- GraphCodeBERT-integrated ranker
- Heuristic vs GraphCodeBERT comparison tool

## What Changed Recently

- GraphCodeBERT was installed and successfully loaded locally.
- GraphCodeBERT was integrated into the offline scorer as the first learned ranking layer.
- A `compare-rankers` tool was added to compare heuristic ranking versus GraphCodeBERT ranking on the same repo/diff.
- The comparison run showed non-trivial reordering, which means the model is contributing signal instead of simply reproducing heuristics.

## Current MVP

The MVP is an offline scorer that can:

- Build or load a fused graph
- Stitch cross-language system seams
- Compute diff-aware candidate paths
- Rank risky findings
- Verify findings before surfacing them
- Produce artifact outputs for developer review and future model fine-tuning

### Current Artifact Outputs

- `violations.json`
- `verifier_audit.json`
- `reasoner_queue.jsonl`
- `ranker_examples.jsonl`
- `reasoner_examples.jsonl`
- `report.md`

## Business Logic Value

This project is moving toward a product that tells teams:

- What changed structurally
- What contract may now be broken
- What systems are affected
- Whether the issue is verified or only suspected
- Where the witness path is
- Which seam actually failed

That is more valuable than simply drawing dependency maps, because teams pay for confidence around risky changes, not just visibility.

## Next Step

The next step is evaluation and data collection.

Immediate next steps:

- Review the promoted and demoted candidates from `compare-rankers`
- Determine whether GraphCodeBERT improves top-of-list precision
- Label strong and weak ranking outcomes
- Accumulate verifier-resolved examples
- Prepare GraphCodeBERT fine-tuning data from real scorer runs

## Training Roadmap

### Phase 0

- Use heuristic + GraphCodeBERT blended ranking
- Collect ranker and reasoner examples
- Keep verifier as the gate

### Phase 1

- Fine-tune GraphCodeBERT on verifier-resolved ranking outcomes
- Improve candidate ordering

### Phase 2

- Fine-tune Gemma on evidence-pack -> structured-JSON outputs
- Still keep deterministic verification in front of any surfaced finding

## Bottom Line

Dependency Map OS is becoming a verifier-first change-risk and contract-analysis engine.

The graph is the substrate.  
The product is the decision pipeline built on top of it.
