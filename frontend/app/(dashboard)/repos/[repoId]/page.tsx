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
  const initialSnapshot =
    ast.ok &&
    ast.data &&
    typeof ast.data === "object" &&
    ast.data !== null &&
    "snapshot" in ast.data
      ? ((ast.data as SnapshotEnvelope).snapshot ?? null)
      : null;

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 md:px-8">
      <h1 className="text-2xl font-semibold tracking-tight">Repository</h1>
      <p className="mt-1 font-mono text-sm text-muted-foreground">{resolvedRepoId ?? repoId}</p>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Latest analysis</CardTitle>
          <CardDescription>Most recent completed or running job for this repo.</CardDescription>
        </CardHeader>
        <CardContent>
          {latest.ok ? (
            <pre className="max-h-96 overflow-auto rounded-lg border border-border bg-muted/30 p-3 text-xs">
              {JSON.stringify(latest.data, null, 2)}
            </pre>
          ) : (
            <p className="text-sm text-muted-foreground">{latest.error}</p>
          )}
        </CardContent>
      </Card>

      <RepoAstPanel
        repoId={resolvedRepoId ?? repoId}
        initialSnapshot={initialSnapshot as AstSnapshot | null}
        initialError={ast.ok || ast.error === "No AST snapshot found" ? null : ast.error}
      />

      <Link
        href="/dashboard"
        className="mt-8 inline-block text-sm font-medium text-primary hover:underline"
      >
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
