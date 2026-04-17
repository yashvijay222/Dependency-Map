# Security review checklist (Phase 6)

Use this checklist before a production launch or major release.

## Authentication and authorization

- [ ] Every route under `backend/app/routers/` validates org/repo scope (pattern: [backend/app/routers/analyses.py](backend/app/routers/analyses.py) `_assert_repo_org_access` / `_assert_analysis_access`).
- [ ] API keys cannot perform user-only actions (e.g. finding reviews require JWT user in [backend/app/routers/analyses.py](backend/app/routers/analyses.py)).
- [ ] GitHub webhook signature verification enabled in production (`GITHUB_WEBHOOK_SECRET`).

## Row-level security (Supabase)

- [ ] Policies exist for `findings`, `finding_reviews`, `pr_analyses`, `graph_artifacts`, `analysis_plans`, `github_webhook_deliveries` (service-role-only where appropriate).
- [ ] Browser-facing Supabase keys are **anon** only; service role never shipped to the client.

## Secrets and rotation

- [ ] `.env` never committed; rotation procedure documented for GitHub App private key and Supabase service role key.
- [ ] Clone URLs with `x-access-token` never logged ([backend/app/services/git_workspace.py](backend/app/services/git_workspace.py)).

## Abuse and cost

- [ ] Rate limits on public endpoints ([backend/app/limiter.py](backend/app/limiter.py)).
- [ ] GitHub API retry/backoff verified under load ([backend/app/services/github_client.py](backend/app/services/github_client.py)).
- [ ] `CPG_REASONER_MAX_PACKS` / org budgets prevent runaway LLM cost.

## Webhooks

- [ ] `X-GitHub-Delivery` dedupe table populated to prevent replay amplification ([backend/app/routers/webhooks.py](backend/app/routers/webhooks.py)).
