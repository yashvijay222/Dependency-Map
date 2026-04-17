-- Gated PR-risk analysis: plans, events, findings, audits, graph artifacts.

alter table public.pr_analyses
  add column if not exists outcome text
    check (outcome in ('completed_ok', 'completed_degraded', 'failed')),
  add column if not exists mode text,
  add column if not exists plan_id uuid,
  add column if not exists task_graph_state jsonb not null default '{}'::jsonb,
  add column if not exists verified_count int not null default 0,
  add column if not exists withheld_count int not null default 0,
  add column if not exists partial_outputs jsonb not null default '[]'::jsonb,
  add column if not exists rerun_of_analysis_id uuid references public.pr_analyses (id) on delete set null;

create table if not exists public.analysis_plans (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.pr_analyses (id) on delete cascade,
  repo_id uuid not null references public.repositories (id) on delete cascade,
  plan_type text not null default 'gated_pr_risk_v1',
  analysis_mode text not null,
  task_graph_json jsonb not null,
  reason_json jsonb not null default '{}'::jsonb,
  disabled_subtasks jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  unique (run_id)
);

create index if not exists analysis_plans_repo_created
  on public.analysis_plans (repo_id, created_at desc);

alter table public.analysis_plans enable row level security;

create policy "Members see analysis plans"
  on public.analysis_plans for select
  using (
    exists (
      select 1 from public.repositories r
      join public.organization_members m on m.org_id = r.org_id
      where r.id = analysis_plans.repo_id and m.user_id = auth.uid()
    )
  );

create table if not exists public.analysis_run_events (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.pr_analyses (id) on delete cascade,
  repo_id uuid not null references public.repositories (id) on delete cascade,
  task_id text not null,
  event_type text not null,
  gate text,
  attempt int not null default 1,
  error_code text,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists analysis_run_events_run_created
  on public.analysis_run_events (run_id, created_at desc);

alter table public.analysis_run_events enable row level security;

create policy "Members see analysis events"
  on public.analysis_run_events for select
  using (
    exists (
      select 1 from public.repositories r
      join public.organization_members m on m.org_id = r.org_id
      where r.id = analysis_run_events.repo_id and m.user_id = auth.uid()
    )
  );

create table if not exists public.graph_artifacts (
  id uuid primary key default gen_random_uuid(),
  analysis_id uuid not null references public.pr_analyses (id) on delete cascade,
  repo_id uuid not null references public.repositories (id) on delete cascade,
  commit_sha text,
  kind text not null,
  storage_bucket text,
  object_key text,
  content_sha256 text,
  byte_size bigint,
  compression text,
  preview_jsonb jsonb not null default '{}'::jsonb,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists graph_artifacts_analysis_kind
  on public.graph_artifacts (analysis_id, kind, created_at desc);

alter table public.graph_artifacts enable row level security;

create policy "Members see graph artifacts"
  on public.graph_artifacts for select
  using (
    exists (
      select 1 from public.repositories r
      join public.organization_members m on m.org_id = r.org_id
      where r.id = graph_artifacts.repo_id and m.user_id = auth.uid()
    )
  );

create table if not exists public.findings (
  id uuid primary key default gen_random_uuid(),
  analysis_id uuid not null references public.pr_analyses (id) on delete cascade,
  repo_id uuid not null references public.repositories (id) on delete cascade,
  finding_key text not null,
  invariant_id text not null,
  severity text not null,
  status text not null
    check (status in ('candidate', 'verified', 'withheld', 'dismissed', 'superseded')),
  withhold_reason text,
  rank_score double precision,
  rank_phase text,
  candidate_json jsonb not null default '{}'::jsonb,
  verification_json jsonb not null default '{}'::jsonb,
  reasoner_json jsonb not null default '{}'::jsonb,
  provenance jsonb not null default '[]'::jsonb,
  summary_json jsonb not null default '{}'::jsonb,
  surfaced_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (analysis_id, finding_key)
);

create index if not exists findings_analysis_status_created
  on public.findings (analysis_id, status, created_at desc);

alter table public.findings enable row level security;

create policy "Members see findings"
  on public.findings for select
  using (
    exists (
      select 1 from public.repositories r
      join public.organization_members m on m.org_id = r.org_id
      where r.id = findings.repo_id and m.user_id = auth.uid()
    )
  );

create table if not exists public.verifier_audits (
  id uuid primary key default gen_random_uuid(),
  analysis_id uuid not null references public.pr_analyses (id) on delete cascade,
  repo_id uuid not null references public.repositories (id) on delete cascade,
  finding_id uuid not null references public.findings (id) on delete cascade,
  checks_run_json jsonb not null default '[]'::jsonb,
  passed_checks_json jsonb not null default '[]'::jsonb,
  failed_checks_json jsonb not null default '[]'::jsonb,
  graph_artifact_ids uuid[] not null default '{}'::uuid[],
  audit_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists verifier_audits_analysis_created
  on public.verifier_audits (analysis_id, created_at desc);

alter table public.verifier_audits enable row level security;

create policy "Members see verifier audits"
  on public.verifier_audits for select
  using (
    exists (
      select 1 from public.repositories r
      join public.organization_members m on m.org_id = r.org_id
      where r.id = verifier_audits.repo_id and m.user_id = auth.uid()
    )
  );

create or replace function public.dm_set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists dm_findings_set_updated_at on public.findings;
create trigger dm_findings_set_updated_at
  before update on public.findings
  for each row execute function public.dm_set_updated_at();

alter table public.pr_analyses
  add constraint pr_analyses_plan_fk
  foreign key (plan_id) references public.analysis_plans (id) on delete set null;
