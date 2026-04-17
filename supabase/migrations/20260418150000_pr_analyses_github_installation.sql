-- Snapshot GitHub App installation on each PR analysis row (Phase 3A).
alter table public.pr_analyses
  add column if not exists github_installation_id bigint;
