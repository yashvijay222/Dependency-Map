-- Allow members to update their own finding review rows (client-side upserts / edits).
create policy "Members update own reviews"
  on public.finding_reviews for update
  using (
    auth.uid() = user_id
    and exists (
      select 1
      from public.findings f
      join public.repositories r on r.id = f.repo_id
      join public.organization_members m on m.org_id = r.org_id
      where f.id = finding_reviews.finding_id and m.user_id = auth.uid()
    )
  )
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
