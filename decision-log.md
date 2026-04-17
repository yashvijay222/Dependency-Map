# Decision Log

- 2026-04-17 (prod-ready program)
  Decision: GitHub Check Run conclusions map to `success` only when analysis `outcome` is `completed_ok`; otherwise `neutral` (or `failure` only for hard `failed`).
  Reason: Product is advisory pre-merge; avoid red X on healthy PRs that still have withheld findings.

- 2026-04-17 (prod-ready program)
  Decision: `pr_analyses` dedupe key is `(repo_id, pr_number, head_sha)` — same push updates the row and re-queues analysis instead of inserting duplicates.
  Reason: Stable deep links and idempotent GitHub webhooks.

- 2026-04-17 (prod-ready program)
  Decision: Dismissals merge into `findings.summary_json` with `dismissed_at`, `dismissed_by_user_id`, and `dismissed_reason` instead of overwriting prior summary.
  Reason: Audit trail for trust / compliance without a separate dismissals table in v1.

- 2026-04-16 23:20 CDT
  Decision: Use GraphCodeBERT as the first learned model in the pipeline.
  Reason: It improves candidate ranking before long-context reasoning and is lightweight enough to run locally.

- 2026-04-16 23:18 CDT
  Decision: Keep the verifier as the trust boundary.
  Reason: Model output is helpful for ranking and explanation, but findings should only be surfaced after deterministic verification.

- 2026-04-16 23:15 CDT
  Decision: Use a blended ranking strategy for now.
  Reason: Combining GraphCodeBERT scoring with heuristics gives a stable phase-0 ranking path while training data is still sparse.

- 2026-04-16 23:10 CDT
  Decision: Add a heuristic-vs-GraphCodeBERT comparison command.
  Reason: Before fine-tuning, the team needs a way to measure whether the model actually improves top-of-list ranking quality.

- 2026-04-16 23:05 CDT
  Decision: Add a labeling workflow from comparison outputs.
  Reason: The project needs reviewer-labeled examples to fine-tune GraphCodeBERT on real repo findings instead of synthetic guesses.

- 2026-04-16 23:00 CDT
  Decision: Store generated scorer, comparison, and graph artifacts under `artifacts/` and ignore them in git.
  Reason: These files are generated, often large, and should not pollute source history.

- 2026-04-16 22:55 CDT
  Decision: Provide a dedicated local model setup guide for contributors.
  Reason: New collaborators need a repeatable path for installing GraphCodeBERT and running the scorer without rediscovering the environment steps.

- 2026-04-16 22:50 CDT
  Decision: The immediate next step is manual review, not fine-tuning.
  Reason: The team needs to validate whether GraphCodeBERT promotions and demotions are actually better before training on the outputs.

- 2026-04-16 22:45 CDT
  Note for Yash:
  Please start with [docs/MODEL_SETUP.md](docs/MODEL_SETUP.md), then review [artifacts/ranker-compare/ranker-labels.jsonl](artifacts/ranker-compare/ranker-labels.jsonl) and manually check the `better`, `worse`, and `unclear` labels. The next step for the project is manual checking of promoted and dropped findings before any fine-tuning work.
