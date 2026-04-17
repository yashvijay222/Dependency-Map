-- Phase 2–7: GitHub integration ids, webhook dedupe, finding reviews, optional org eval cache

alter table public.pr_analyses
  add column if not exists github_pr_url text,
  add column if not exists github_check_run_id bigint,
  add column if not exists github_comment_id bigint;

create table if not exists public.github_webhook_deliveries (
  delivery_id text primary key,
  event_type text not null,
  received_at timestamptz not null default now()
);

create index if not exists github_webhook_deliveries_received
  on public.github_webhook_deliveries (received_at desc);

alter table public.github_webhook_deliveries enable row level security;

-- Service role only (no member policy): backend uses service role for dedupe writes
create policy "Service role manages webhook dedupe"
  on public.github_webhook_deliveries
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

create table if not exists public.finding_reviews (
  id uuid primary key default gen_random_uuid(),
  finding_id uuid not null references public.findings (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  label text not null check (label in ('helpful', 'wrong', 'noisy')),
  notes text,
  created_at timestamptz not null default now(),
  unique (finding_id, user_id)
);

create index if not exists finding_reviews_finding_created
  on public.finding_reviews (finding_id, created_at desc);

alter table public.finding_reviews enable row level security;

create policy "Members review findings in their org"
  on public.finding_reviews for select
  using (
    exists (
      select 1
      from public.findings f
      join public.repositories r on r.id = f.repo_id
      join public.organization_members m on m.org_id = r.org_id
      where f.id = finding_reviews.finding_id and m.user_id = auth.uid()
    )
  );

create policy "Members insert own reviews"
  on public.finding_reviews for insert
  with check (
    auth.uid() = user_id
    and exists (
      select 1
      from public.findings f
      join public.repositories r on r.id = f.repo_id
      join public.organization_members m on m.org_id = r.org_id
      where f.id = finding_reviews.finding_id and m.user_id = auth.uid()
    )
  );
