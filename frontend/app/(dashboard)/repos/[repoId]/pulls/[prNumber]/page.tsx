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
  summary_json?: Record<string, unknown>;
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

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
  const newest = analyses.length > 0 ? analyses[0] : null;
  const rollup = newest?.summary_json && isRecord(newest.summary_json) ? newest.summary_json : null;

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 md:px-8">
      <h1 className="text-2xl font-semibold tracking-tight">Pull request analyses</h1>
      <p className="mt-1 font-mono text-sm text-muted-foreground">
        repo {repoId} · PR #{prNumber}
      </p>

      {rollup ? (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-base">Latest run summary</CardTitle>
            <CardDescription>Newest analysis (same order as the list below).</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm sm:grid-cols-2">
            <div className="rounded-md border border-border px-3 py-2">
              <div className="text-xs text-muted-foreground">Verified</div>
              <div className="font-semibold tabular-nums">{String(rollup.verified_findings ?? "—")}</div>
            </div>
            <div className="rounded-md border border-border px-3 py-2">
              <div className="text-xs text-muted-foreground">Withheld</div>
              <div className="font-semibold tabular-nums">{String(rollup.withheld_findings ?? "—")}</div>
            </div>
            <div className="rounded-md border border-border px-3 py-2">
              <div className="text-xs text-muted-foreground">CPG candidates</div>
              <div className="font-semibold tabular-nums">{String(rollup.cpg_candidate_count ?? "—")}</div>
            </div>
            <div className="rounded-md border border-border px-3 py-2">
              <div className="text-xs text-muted-foreground">Cross-repo score</div>
              <div className="font-semibold tabular-nums">
                {String(rollup.aggregate_cross_repo_score ?? rollup.blast_radius_score ?? "—")}
              </div>
            </div>
            {typeof newest?.id === "string" ? (
              <div className="sm:col-span-2">
                <Link
                  href={`/repos/${repoId}/analyses/${newest.id}`}
                  className="text-sm font-medium text-primary hover:underline"
                >
                  Open latest analysis detail
                </Link>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

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
