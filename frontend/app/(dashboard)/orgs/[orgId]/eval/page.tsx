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
