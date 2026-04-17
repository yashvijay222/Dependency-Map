import Link from "next/link";
import { FindingsBoard } from "@/components/finding-board";
import { apiFetchOptional } from "@/lib/api";
import { isValidUuid } from "@/lib/uuid";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type JsonRecord = Record<string, unknown>;

export default async function AnalysisPage({
  params,
}: {
  params: Promise<{ repoId: string; analysisId: string }>;
}) {
  const { repoId, analysisId } = await params;
  if (!isValidUuid(repoId) || !isValidUuid(analysisId)) {
    return (
      <main className="mx-auto max-w-6xl px-4 py-8 md:px-8">
        <Card>
          <CardContent className="pt-6 text-sm">
            Repository and analysis IDs in the URL must be UUIDs. Sample paths like `/repos/demo`
            are placeholders only.
          </CardContent>
        </Card>
      </main>
    );
  }

  const [analysis, plan, findings, audit, graph] = await Promise.all([
    apiFetchOptional(`/v1/repos/${repoId}/analyses/${analysisId}`),
    apiFetchOptional(`/v1/repos/${repoId}/analyses/${analysisId}/plan`),
    apiFetchOptional(`/v1/repos/${repoId}/analyses/${analysisId}/findings`),
    apiFetchOptional(`/v1/repos/${repoId}/analyses/${analysisId}/audit`),
    apiFetchOptional(`/v1/repos/${repoId}/analyses/${analysisId}/graph`),
  ]);

  const analysisData = analysis.ok && isRecord(analysis.data) ? analysis.data : null;
  const summary =
    analysisData && isRecord(analysisData.summary_json)
      ? (analysisData.summary_json as JsonRecord)
      : null;
  const planData = plan.ok && isRecord(plan.data) ? plan.data : null;
  const findingsData = findings.ok && isRecord(findings.data) ? findings.data : null;
  const auditData = audit.ok && isRecord(audit.data) ? audit.data : null;
  const graphData = graph.ok && isRecord(graph.data) ? graph.data : null;
  const cpgStatus = summary && isRecord(summary.cpg_status) ? (summary.cpg_status as JsonRecord) : null;
  const stitchOverview =
    summary && isRecord(summary.stitch_overview) ? (summary.stitch_overview as JsonRecord) : null;
  const lowStitcherCoverage =
    stitchOverview?.low_stitcher_coverage === true ||
    cpgStatus?.low_stitcher_coverage === true ||
    summary?.low_stitcher_coverage === true;
  const disabledSubtasks = asArray(planData?.disabled_subtasks);
  const cpgArtifact = asArray(graphData?.artifacts).find((item) => {
    const row = isRecord(item) ? item : {};
    return row.kind === "base_cpg";
  });
  const cpgArtifactRecord = isRecord(cpgArtifact) ? cpgArtifact : null;
  const cpgDownloadUrl =
    typeof cpgArtifactRecord?.download_url === "string" ? cpgArtifactRecord.download_url : null;
  const prNumber =
    typeof analysisData?.pr_number === "number"
      ? analysisData.pr_number
      : typeof analysisData?.pr_number === "string"
        ? Number.parseInt(analysisData.pr_number, 10)
        : null;
  const prHubHref =
    prNumber !== null && !Number.isNaN(prNumber) ? `/repos/${repoId}/pulls/${prNumber}` : null;
  const presentedFindings = asArray(findingsData?.presented);

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 md:px-8">
      <h1 className="text-2xl font-semibold tracking-tight">PR Risk Analysis</h1>
      <p className="mt-1 font-mono text-sm text-muted-foreground">
        {repoId} / {analysisId}
      </p>
      {prHubHref ? (
        <p className="mt-2 text-sm">
          <Link href={prHubHref} className="font-medium text-primary hover:underline">
            Open PR timeline
          </Link>
        </p>
      ) : null}

      {lowStitcherCoverage ? (
        <div className="mt-6 rounded-md border border-amber-500/35 bg-amber-500/10 px-4 py-3 text-sm text-amber-950 dark:text-amber-50">
          <p className="font-medium">Limited stitcher coverage</p>
          <p className="mt-1 text-muted-foreground">
            Contract and route matching may be incomplete for this run. Treat blast-radius and contract edges as
            lower confidence until coverage improves.
          </p>
        </div>
      ) : null}

      <section className="mt-8 grid gap-4 md:grid-cols-3">
        <MetricCard label="Status" value={stringOrFallback(analysisData?.status)} />
        <MetricCard label="Outcome" value={stringOrFallback(analysisData?.outcome)} />
        <MetricCard label="Mode" value={stringOrFallback(analysisData?.mode ?? summary?.analysis_mode)} />
      </section>

      <section className="mt-8 grid gap-6 lg:grid-cols-[1.35fr_0.95fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">PR Overview</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <OverviewList
                rows={[
                  ["Base SHA", stringOrFallback(analysisData?.base_sha)],
                  ["Head SHA", stringOrFallback(analysisData?.head_sha)],
                  ["Blast Radius Score", stringOrFallback(summary?.blast_radius_score)],
                  ["Confidence", stringOrFallback(summary?.confidence)],
                  ["Verified Findings", stringOrFallback(summary?.verified_findings)],
                  ["Withheld Findings", stringOrFallback(summary?.withheld_findings)],
                ]}
              />
              <JsonArraySection title="Changed Files" value={summary?.changed_files} />
              <JsonArraySection title="Suggested Reviewers" value={summary?.suggested_reviewers} />
              <JsonArraySection title="Risks" value={summary?.risks} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">CPG / contracts</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <OverviewList
                rows={[
                  ["Status", stringOrFallback(cpgStatus?.mode)],
                  ["Reason", stringOrFallback(cpgStatus?.reason)],
                  ["Diff source", stringOrFallback(summary?.cpg_diff_source)],
                  ["Candidates", stringOrFallback(summary?.cpg_candidate_count)],
                  ["Surfaced", stringOrFallback(summary?.cpg_surfaced_count)],
                ]}
              />
              {cpgDownloadUrl ? (
                <a
                  href={cpgDownloadUrl}
                  className="inline-block text-xs font-medium text-primary hover:underline"
                >
                  Open base_cpg artifact
                </a>
              ) : (
                <p className="text-xs text-muted-foreground">No base_cpg artifact for this run.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Findings</CardTitle>
            </CardHeader>
            <CardContent>
              <FindingsBoard repoId={repoId} presented={presentedFindings} />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Plan</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <OverviewList
                rows={[
                  ["Plan Type", stringOrFallback(planData?.plan_type)],
                  ["Analysis Mode", stringOrFallback(planData?.analysis_mode)],
                ]}
              />
              <JsonArraySection title="Disabled subtasks" value={disabledSubtasks} limit={12} />
              <TaskGraphList nodes={asArray((planData?.task_graph_json as JsonRecord | undefined)?.nodes)} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Audit</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <JsonArraySection title="Run Events" value={auditData?.events} limit={8} />
              <JsonArraySection title="Verifier Audits" value={auditData?.verifier_audits} limit={6} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Graph Artifacts</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {asArray(graphData?.artifacts).length > 0 ? (
                asArray(graphData?.artifacts).map((item, index) => {
                  const artifact = isRecord(item) ? item : {};
                  const downloadUrl =
                    typeof artifact.download_url === "string" ? artifact.download_url : null;
                  return (
                    <div key={index} className="rounded-md border p-3">
                      <div className="font-medium">{stringOrFallback(artifact.kind)}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {stringOrFallback(artifact.commit_sha)} · {stringOrFallback(artifact.byte_size)}
                      </div>
                      {isRecord(artifact.preview_jsonb) ? (
                        <pre className="mt-2 overflow-auto text-xs">
                          {JSON.stringify(artifact.preview_jsonb, null, 2)}
                        </pre>
                      ) : null}
                      {downloadUrl ? (
                        <a href={downloadUrl} className="mt-2 inline-block text-xs text-primary hover:underline">
                          Open signed artifact URL
                        </a>
                      ) : (
                        <p className="mt-2 text-xs text-muted-foreground">Metadata only</p>
                      )}
                    </div>
                  );
                })
              ) : (
                <p className="text-muted-foreground">No graph artifacts recorded.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </section>

      <Link
        href={`/repos/${repoId}`}
        className="mt-8 inline-block text-sm font-medium text-primary hover:underline"
      >
        Back to repo
      </Link>
    </main>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent className="text-lg font-semibold">{value}</CardContent>
    </Card>
  );
}

function OverviewList({ rows }: { rows: [string, string][] }) {
  return (
    <div className="space-y-2">
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-center justify-between gap-4 border-b pb-2 text-sm last:border-b-0 last:pb-0">
          <span className="text-muted-foreground">{label}</span>
          <span className="font-mono text-xs text-right">{value}</span>
        </div>
      ))}
    </div>
  );
}

function TaskGraphList({ nodes }: { nodes: unknown[] }) {
  if (nodes.length === 0) {
    return <p className="text-muted-foreground">No task graph available.</p>;
  }
  return (
    <div className="space-y-2">
      {nodes.map((item, index) => {
        const node = isRecord(item) ? item : {};
        return (
          <div key={index} className="rounded-md border p-3">
            <div className="flex items-center justify-between gap-3">
              <span className="font-medium">{stringOrFallback(node.id)}</span>
              <span className="flex shrink-0 items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
                {node.optional ? (
                  <span className="rounded border border-dashed px-1.5 py-0.5 normal-case">optional</span>
                ) : null}
                <span>{stringOrFallback(node.status)}</span>
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{stringOrFallback(node.reason)}</p>
          </div>
        );
      })}
    </div>
  );
}

function JsonArraySection({
  title,
  value,
  limit,
}: {
  title: string;
  value: unknown;
  limit?: number;
}) {
  const items = asArray(value);
  if (items.length === 0) return null;
  const shown = typeof limit === "number" ? items.slice(0, limit) : items;
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      <ul className="space-y-2">
        {shown.map((item, index) => (
          <li key={index} className="rounded-md border p-2 text-xs">
            {typeof item === "string" ? item : JSON.stringify(item, null, 2)}
          </li>
        ))}
      </ul>
    </div>
  );
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringOrFallback(value: unknown): string {
  if (value === null || value === undefined || value === "") return "n/a";
  return typeof value === "string" ? value : JSON.stringify(value);
}
