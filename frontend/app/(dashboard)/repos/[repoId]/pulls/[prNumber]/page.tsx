import Link from "next/link";

import { apiFetchOptional } from "@/lib/api";
import { isValidUuid } from "@/lib/uuid";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type AnalysisRow = {
  id?: string;
  status?: string;
  outcome?: string;
  head_sha?: string;
  base_sha?: string;
  created_at?: string;
};

export default async function PullRequestAnalysesPage({
  params,
}: {
  params: Promise<{ repoId: string; prNumber: string }>;
}) {
  const { repoId, prNumber: prRaw } = await params;
  const prNumber = Number.parseInt(prRaw, 10);
  if (!isValidUuid(repoId) || Number.isNaN(prNumber)) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-8 md:px-8">
        <Card>
          <CardContent className="pt-6 text-sm">
            Use a repository UUID and numeric PR number in the URL (for example from the GitHub PR page or your
            database).
          </CardContent>
        </Card>
      </main>
    );
  }

  const res = await apiFetchOptional(`/v1/repos/${repoId}/pulls/${prNumber}/analyses`);
  const payload =
    res.ok && res.data && typeof res.data === "object" && res.data !== null && "analyses" in res.data
      ? (res.data as { analyses: AnalysisRow[] })
      : null;
  const analyses = Array.isArray(payload?.analyses) ? payload!.analyses : [];

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 md:px-8">
      <h1 className="text-2xl font-semibold tracking-tight">Pull request analyses</h1>
      <p className="mt-1 font-mono text-sm text-muted-foreground">
        repo {repoId} · PR #{prNumber}
      </p>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Runs</CardTitle>
          <CardDescription>Newest first (up to 50).</CardDescription>
        </CardHeader>
        <CardContent>
          {!res.ok ? (
            <p className="text-sm text-muted-foreground">{res.error}</p>
          ) : analyses.length === 0 ? (
            <p className="text-sm text-muted-foreground">No analyses for this PR yet.</p>
          ) : (
            <ul className="divide-y divide-border rounded-lg border border-border">
              {analyses.map((row) => {
                const id = typeof row.id === "string" ? row.id : "";
                return (
                  <li key={id || JSON.stringify(row)} className="px-4 py-3 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <span className="font-medium">{row.status ?? "—"}</span>
                        <span className="ml-2 text-muted-foreground">{row.outcome ?? ""}</span>
                      </div>
                      {id ? (
                        <Link
                          href={`/repos/${repoId}/analyses/${id}`}
                          className="text-xs font-medium text-primary hover:underline"
                        >
                          Open analysis
                        </Link>
                      ) : null}
                    </div>
                    <div className="mt-1 font-mono text-[11px] text-muted-foreground">
                      {row.head_sha ? `head ${row.head_sha.slice(0, 7)}` : ""}
                      {row.base_sha ? ` · base ${row.base_sha.slice(0, 7)}` : ""}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      <Link href={`/repos/${repoId}`} className="mt-8 inline-block text-sm font-medium text-primary hover:underline">
        Back to repository
      </Link>
    </main>
  );
}
