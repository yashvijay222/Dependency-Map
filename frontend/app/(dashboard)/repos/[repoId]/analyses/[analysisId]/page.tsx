import Link from "next/link";
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

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 md:px-8">
      <h1 className="text-2xl font-semibold tracking-tight">PR Risk Analysis</h1>
      <p className="mt-1 font-mono text-sm text-muted-foreground">
        {repoId} / {analysisId}
      </p>

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
              <CardTitle className="text-base">Findings Review</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <FindingsColumn
                title="Verified"
                items={asArray(findingsData?.verified)}
                empty="No verified findings yet."
              />
              <FindingsColumn
                title="Withheld"
                items={asArray(findingsData?.withheld)}
                empty="No withheld findings."
              />
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

function FindingsColumn({
  title,
  items,
  empty,
}: {
  title: string;
  items: unknown[];
  empty: string;
}) {
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold">{title}</h3>
      {items.length > 0 ? (
        items.map((item, index) => {
          const finding = isRecord(item) ? item : {};
          return (
            <div key={index} className="rounded-md border p-3">
              <div className="font-medium">{stringOrFallback(finding.invariant_id)}</div>
              <div className="mt-1 text-xs text-muted-foreground">
                {stringOrFallback(finding.severity)} · {stringOrFallback(finding.status)}
              </div>
              {isRecord(finding.summary_json) ? (
                <pre className="mt-2 overflow-auto text-xs">
                  {JSON.stringify(finding.summary_json, null, 2)}
                </pre>
              ) : null}
            </div>
          );
        })
      ) : (
        <p className="text-sm text-muted-foreground">{empty}</p>
      )}
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
              <span className="text-xs uppercase tracking-wide text-muted-foreground">
                {stringOrFallback(node.status)}
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
