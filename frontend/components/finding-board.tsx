"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { apiBase } from "@/lib/api-base";
import { createClient } from "@/lib/supabase/client";

export type PresentedFinding = {
  id?: string;
  title?: string;
  verdict?: unknown;
  status?: string;
  severity?: string;
  invariant_id?: string;
  file_anchors?: string[];
  caveats?: unknown[];
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

async function authJsonHeaders(): Promise<Headers> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const headers = new Headers({
    Accept: "application/json",
    "Content-Type": "application/json",
  });
  if (session?.access_token) {
    headers.set("Authorization", `Bearer ${session.access_token}`);
  }
  return headers;
}

function FindingCard({
  repoId,
  finding,
}: {
  repoId: string;
  finding: PresentedFinding;
}) {
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const fid = typeof finding.id === "string" ? finding.id : null;
  const status = typeof finding.status === "string" ? finding.status : "";
  const caveats = Array.isArray(finding.caveats) ? finding.caveats : [];
  const anchors = Array.isArray(finding.file_anchors) ? finding.file_anchors : [];

  async function dismiss() {
    if (!fid) return;
    const reason = window.prompt("Optional reason for dismissal") ?? "";
    setBusy("dismiss");
    setMessage(null);
    try {
      const headers = await authJsonHeaders();
      const res = await fetch(`${apiBase()}/v1/repos/${repoId}/findings/${fid}`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({ status: "dismissed", reason: reason || undefined }),
      });
      const text = await res.text();
      if (!res.ok) {
        setMessage(text || `Request failed (${res.status})`);
        return;
      }
      setMessage("Dismissed. Refresh the page to see updated status.");
    } finally {
      setBusy(null);
    }
  }

  async function review(label: "helpful" | "wrong" | "noisy") {
    if (!fid) return;
    setBusy(label);
    setMessage(null);
    try {
      const headers = await authJsonHeaders();
      const res = await fetch(`${apiBase()}/v1/repos/${repoId}/findings/${fid}/reviews`, {
        method: "POST",
        headers,
        body: JSON.stringify({ label }),
      });
      const text = await res.text();
      if (!res.ok) {
        setMessage(text || `Request failed (${res.status})`);
        return;
      }
      setMessage("Review saved.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="rounded-md border p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-medium">{finding.title ?? finding.invariant_id ?? "Finding"}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {String(finding.severity ?? "—")} · {status || "—"} · {String(finding.verdict ?? "—")}
          </div>
        </div>
      </div>
      {anchors.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {anchors.map((a) => (
            <span key={a} className="rounded-md border border-border bg-muted/40 px-2 py-0.5 font-mono text-[11px]">
              {a}
            </span>
          ))}
        </div>
      ) : null}
      {caveats.length > 0 ? (
        <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-muted-foreground">
          {caveats.map((c, i) => (
            <li key={i}>{typeof c === "string" ? c : JSON.stringify(c)}</li>
          ))}
        </ul>
      ) : null}
      {fid && status !== "dismissed" ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" disabled={busy !== null} onClick={() => void dismiss()}>
            {busy === "dismiss" ? "…" : "Dismiss"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={busy !== null}
            onClick={() => void review("helpful")}
          >
            {busy === "helpful" ? "…" : "Helpful"}
          </Button>
          <Button type="button" size="sm" variant="secondary" disabled={busy !== null} onClick={() => void review("wrong")}>
            {busy === "wrong" ? "…" : "Wrong"}
          </Button>
          <Button type="button" size="sm" variant="secondary" disabled={busy !== null} onClick={() => void review("noisy")}>
            {busy === "noisy" ? "…" : "Noisy"}
          </Button>
        </div>
      ) : null}
      {message ? <p className="mt-2 text-xs text-muted-foreground">{message}</p> : null}
    </div>
  );
}

export function FindingsBoard({
  repoId,
  presented,
}: {
  repoId: string;
  presented: unknown[];
}) {
  const rows: PresentedFinding[] = presented.filter((p): p is PresentedFinding => isRecord(p));
  const verified = rows.filter((r) => r.status === "verified");
  const withheld = rows.filter((r) => r.status === "withheld");

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="space-y-3">
        <h3 className="text-sm font-semibold">Verified</h3>
        {verified.length > 0 ? (
          verified.map((f) => <FindingCard key={String(f.id)} repoId={repoId} finding={f} />)
        ) : (
          <p className="text-sm text-muted-foreground">No verified findings yet.</p>
        )}
      </div>
      <div className="space-y-3">
        <h3 className="text-sm font-semibold">Withheld</h3>
        {withheld.length > 0 ? (
          withheld.map((f) => <FindingCard key={String(f.id)} repoId={repoId} finding={f} />)
        ) : (
          <p className="text-sm text-muted-foreground">No withheld findings.</p>
        )}
      </div>
    </div>
  );
}
