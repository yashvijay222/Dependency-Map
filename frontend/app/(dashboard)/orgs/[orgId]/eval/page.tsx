import Link from "next/link";

import { apiFetchOptional } from "@/lib/api";
import { isValidUuid } from "@/lib/uuid";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default async function OrgEvalPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  const summary = isValidUuid(orgId)
    ? await apiFetchOptional(`/v1/orgs/${orgId}/eval-summary`)
    : { ok: false as const, error: "Organization id must be a UUID from your workspace." };

  const counts =
    summary.ok &&
    summary.data &&
    typeof summary.data === "object" &&
    summary.data !== null &&
    "counts" in summary.data
      ? ((summary.data as { counts: Record<string, number> }).counts ?? {})
      : {};
  const total =
    summary.ok &&
    summary.data &&
    typeof summary.data === "object" &&
    summary.data !== null &&
    "total" in summary.data
      ? Number((summary.data as { total: number }).total)
      : 0;
  const findingsByInvariant =
    summary.ok &&
    summary.data &&
    typeof summary.data === "object" &&
    summary.data !== null &&
    "findings_by_invariant" in summary.data
      ? ((summary.data as { findings_by_invariant: Record<string, number> }).findings_by_invariant ?? {})
      : {};
  const findingsByStatus =
    summary.ok &&
    summary.data &&
    typeof summary.data === "object" &&
    summary.data !== null &&
    "findings_by_status" in summary.data
      ? ((summary.data as { findings_by_status: Record<string, number> }).findings_by_status ?? {})
      : {};
  const invTotal = Object.values(findingsByInvariant).reduce((a, b) => a + b, 0);
  const statusTotal = Object.values(findingsByStatus).reduce((a, b) => a + b, 0);

  return (
    <main className="mx-auto max-w-3xl px-4 py-8 md:px-8">
      <h1 className="text-2xl font-semibold tracking-tight">Finding reviews</h1>
      <p className="mt-1 text-sm text-muted-foreground">Aggregated labels across repositories in this org.</p>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Label counts</CardTitle>
          <CardDescription>From the finding reviews API (authenticated user session).</CardDescription>
        </CardHeader>
        <CardContent>
          {!summary.ok ? (
            <p className="text-sm text-muted-foreground">{summary.error}</p>
          ) : total === 0 ? (
            <p className="text-sm text-muted-foreground">No reviews recorded yet.</p>
          ) : (
            <dl className="grid gap-2 text-sm sm:grid-cols-2">
              {Object.entries(counts).map(([label, n]) => (
                <div key={label} className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                  <dt className="font-medium">{label}</dt>
                  <dd className="tabular-nums text-muted-foreground">{n}</dd>
                </div>
              ))}
            </dl>
          )}
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Findings by invariant</CardTitle>
          <CardDescription>Open findings in this org (up to 5000 sampled for the API).</CardDescription>
        </CardHeader>
        <CardContent>
          {!summary.ok ? (
            <p className="text-sm text-muted-foreground">{summary.error}</p>
          ) : invTotal === 0 ? (
            <p className="text-sm text-muted-foreground">No findings in org yet.</p>
          ) : (
            <BarList data={findingsByInvariant} />
          )}
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Findings by status</CardTitle>
          <CardDescription>Same sample as invariant breakdown.</CardDescription>
        </CardHeader>
        <CardContent>
          {!summary.ok ? (
            <p className="text-sm text-muted-foreground">{summary.error}</p>
          ) : statusTotal === 0 ? (
            <p className="text-sm text-muted-foreground">No findings in org yet.</p>
          ) : (
            <BarList data={findingsByStatus} />
          )}
        </CardContent>
      </Card>

      <div className="mt-8 flex flex-wrap gap-4 text-sm">
        <Link href={`/orgs/${orgId}/repos`} className="text-primary hover:underline">
          Repositories
        </Link>
        <Link href={`/orgs/${orgId}/settings`} className="text-primary hover:underline">
          Org caps
        </Link>
        <Link href="/dashboard" className="text-primary hover:underline">
          Dashboard
        </Link>
      </div>
    </main>
  );
}

function BarList({ data }: { data: Record<string, number> }) {
  const max = Math.max(1, ...Object.values(data));
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  return (
    <ul className="space-y-3 text-sm">
      {entries.map(([key, n]) => (
        <li key={key}>
          <div className="mb-1 flex justify-between gap-2">
            <span className="truncate font-medium" title={key}>
              {key}
            </span>
            <span className="shrink-0 tabular-nums text-muted-foreground">{n}</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary/80"
              style={{ width: `${Math.round((n / max) * 100)}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
