import Link from "next/link";

import { RepoAstPanel, type AstSnapshot } from "@/components/repo-ast-panel";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetchOptional } from "@/lib/api";
import { isValidUuid } from "@/lib/uuid";

type SnapshotEnvelope = {
  snapshot?: unknown;
};

type RepoLookupPayload = {
  repository?: {
    id?: string;
  };
};

type RepoDetailPayload = {
  repository?: {
    id?: string;
    org_id?: string;
    full_name?: string;
    default_branch?: string;
  };
};

type CrossRepoEdge = {
  source_repo_id?: string;
  target_repo_id?: string;
  edge_kind?: string;
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export default async function RepoPage({
  params,
}: {
  params: Promise<{ repoId: string }>;
}) {
  const { repoId } = await params;
  const resolvedRepoId =
    repoId === "this-repo"
      ? await resolveThisRepoId()
      : isValidUuid(repoId)
        ? repoId
        : null;

  const latest = resolvedRepoId
    ? await apiFetchOptional(`/v1/repos/${resolvedRepoId}/analyses/latest`)
    : {
        ok: false as const,
        error:
          "The API expects a repository UUID in the URL (from your database), not a short name like \"demo\".",
      };
  const ast = resolvedRepoId
    ? await apiFetchOptional(`/v1/repos/${resolvedRepoId}/ast`)
    : {
        ok: false as const,
        error: repoId === "this-repo" ? "Could not resolve the hardcoded repository yet." : "AST snapshots require a repository UUID.",
      };
  const repoMeta = resolvedRepoId ? await apiFetchOptional(`/v1/repos/${resolvedRepoId}`) : { ok: false as const, error: "" };
  const orgId =
    repoMeta.ok &&
    repoMeta.data &&
    typeof repoMeta.data === "object" &&
    repoMeta.data !== null &&
    "repository" in repoMeta.data &&
    isRecord((repoMeta.data as RepoDetailPayload).repository)
      ? String((repoMeta.data as RepoDetailPayload).repository!.org_id ?? "")
      : null;
  const orgIdClean = orgId && orgId.length > 0 ? orgId : null;

  const consumers =
    orgIdClean && resolvedRepoId
      ? await apiFetchOptional(`/v1/orgs/${orgIdClean}/graph/repos/${resolvedRepoId}/consumers`)
      : { ok: false as const, error: "" };

  const drift = resolvedRepoId
    ? await apiFetchOptional(`/v1/repos/${resolvedRepoId}/branches/drift`)
    : { ok: false as const, error: "" };

  const initialSnapshot =
    ast.ok &&
    ast.data &&
    typeof ast.data === "object" &&
    ast.data !== null &&
    "snapshot" in ast.data
      ? ((ast.data as SnapshotEnvelope).snapshot ?? null)
      : null;

  const latestRow = latest.ok && isRecord(latest.data) ? latest.data : null;
  const analysisHref =
    resolvedRepoId && latestRow && typeof latestRow.id === "string"
      ? `/repos/${resolvedRepoId}/analyses/${latestRow.id}`
      : null;
  const prNum = latestRow && typeof latestRow.pr_number === "number" ? latestRow.pr_number : null;
  const prHref =
    resolvedRepoId && prNum !== null && !Number.isNaN(prNum) ? `/repos/${resolvedRepoId}/pulls/${prNum}` : null;
  const ghUrl = latestRow && typeof latestRow.github_pr_url === "string" ? latestRow.github_pr_url : null;
  const latestFetchError = !latest.ok ? latest.error : null;

  const consumerEdges =
    consumers.ok &&
    consumers.data &&
    typeof consumers.data === "object" &&
    consumers.data !== null &&
    "edges" in consumers.data &&
    Array.isArray((consumers.data as { edges: unknown }).edges)
      ? ((consumers.data as { edges: CrossRepoEdge[] }).edges ?? []).slice(0, 40)
      : [];

  const driftSignals =
    drift.ok &&
    drift.data &&
    typeof drift.data === "object" &&
    drift.data !== null &&
    "signals" in drift.data &&
    Array.isArray((drift.data as { signals: unknown }).signals)
      ? ((drift.data as { signals: Record<string, unknown>[] }).signals ?? []).slice(0, 12)
      : [];

  const fullName =
    repoMeta.ok &&
    repoMeta.data &&
    typeof repoMeta.data === "object" &&
    "repository" in repoMeta.data &&
    isRecord((repoMeta.data as RepoDetailPayload).repository)
      ? String((repoMeta.data as RepoDetailPayload).repository!.full_name ?? "")
      : "";

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 md:px-8">
      <h1 className="text-2xl font-semibold tracking-tight">Repository</h1>
      <p className="mt-1 font-mono text-sm text-muted-foreground">{fullName || resolvedRepoId || repoId}</p>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Latest analysis</CardTitle>
          <CardDescription>Most recent job for this repository.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {latest.ok && latestRow ? (
            <>
              <div className="flex flex-wrap gap-4 text-xs">
                <div>
                  <div className="text-muted-foreground">Status</div>
                  <div className="font-medium">{String(latestRow.status ?? "—")}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Outcome</div>
                  <div className="font-medium">{String(latestRow.outcome ?? "—")}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Mode</div>
                  <div className="font-medium">{String(latestRow.mode ?? "—")}</div>
                </div>
              </div>
              <div className="flex flex-wrap gap-3 text-xs">
                {analysisHref ? (
                  <Link href={analysisHref} className="font-medium text-primary hover:underline">
                    Open analysis
                  </Link>
                ) : null}
                {prHref ? (
                  <Link href={prHref} className="font-medium text-primary hover:underline">
                    PR timeline in app
                  </Link>
                ) : null}
                {ghUrl ? (
                  <a href={ghUrl} className="font-medium text-primary hover:underline" target="_blank" rel="noreferrer">
                    View on GitHub
                  </a>
                ) : null}
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">{latestFetchError}</p>
          )}
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Branch drift signals</CardTitle>
          <CardDescription>Recent default-branch vs feature-branch comparisons.</CardDescription>
        </CardHeader>
        <CardContent>
          {!drift.ok ? (
            <p className="text-sm text-muted-foreground">{drift.error}</p>
          ) : driftSignals.length === 0 ? (
            <p className="text-sm text-muted-foreground">No drift rows yet.</p>
          ) : (
            <ul className="space-y-2 text-xs">
              {driftSignals.map((s, i) => (
                <li key={i} className="rounded-md border border-border p-2 font-mono">
                  {String(s.branch_a ?? "")} ↔ {String(s.branch_b ?? "")} · overlap {String(s.overlap_score ?? "—")}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Cross-repo consumers</CardTitle>
          <CardDescription>Repos that depend on this repository within the org graph.</CardDescription>
        </CardHeader>
        <CardContent>
          {!orgIdClean ? (
            <p className="text-sm text-muted-foreground">Org context unavailable.</p>
          ) : !consumers.ok ? (
            <p className="text-sm text-muted-foreground">{consumers.error}</p>
          ) : consumerEdges.length === 0 ? (
            <p className="text-sm text-muted-foreground">No incoming cross-repo edges.</p>
          ) : (
            <ul className="space-y-2 text-xs font-mono">
              {consumerEdges.map((e, i) => (
                <li key={i} className="rounded-md border border-border p-2">
                  {e.edge_kind ?? "edge"} · source {String(e.source_repo_id ?? "").slice(0, 8)}…
                </li>
              ))}
            </ul>
          )}
          {orgIdClean ? (
            <p className="mt-3 text-xs text-muted-foreground">
              Org tools:{" "}
              <Link href={`/orgs/${orgIdClean}/eval`} className="text-primary hover:underline">
                Eval summary
              </Link>
              {" · "}
              <Link href={`/orgs/${orgIdClean}/settings`} className="text-primary hover:underline">
                Org caps
              </Link>
            </p>
          ) : null}
        </CardContent>
      </Card>

      <RepoAstPanel
        repoId={resolvedRepoId ?? repoId}
        initialSnapshot={initialSnapshot as AstSnapshot | null}
        initialError={ast.ok || ast.error === "No AST snapshot found" ? null : ast.error}
      />

      <Link href="/dashboard" className="mt-8 inline-block text-sm font-medium text-primary hover:underline">
        Dashboard
      </Link>
    </main>
  );
}

async function resolveThisRepoId(): Promise<string | null> {
  const res = await apiFetchOptional("/v1/repos/lookup?name=Dependency-Map");
  if (
    res.ok &&
    res.data &&
    typeof res.data === "object" &&
    res.data !== null &&
    "repository" in res.data
  ) {
    const repo = (res.data as RepoLookupPayload).repository;
    if (typeof repo?.id === "string") {
      return repo.id;
    }
  }
  return null;
}
