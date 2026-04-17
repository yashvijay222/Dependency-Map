"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  witness_nodes?: string[];
  evidence_links?: { label?: string; url?: string }[];
  witness?: { node_ids?: unknown[]; seam_type?: unknown };
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
  const [dismissOpen, setDismissOpen] = useState(false);
  const [dismissReason, setDismissReason] = useState("");
  const fid = typeof finding.id === "string" ? finding.id : null;
  const status = typeof finding.status === "string" ? finding.status : "";
  const caveats = Array.isArray(finding.caveats) ? finding.caveats : [];
  const anchors = Array.isArray(finding.file_anchors) ? finding.file_anchors : [];
  const witnessNodes = Array.isArray(finding.witness_nodes) ? finding.witness_nodes : [];
  const links = Array.isArray(finding.evidence_links) ? finding.evidence_links : [];
  const rawNodes = finding.witness && Array.isArray(finding.witness.node_ids) ? finding.witness.node_ids : [];

  async function dismissConfirm() {
    if (!fid) return;
    setBusy("dismiss");
    setMessage(null);
    try {
      const headers = await authJsonHeaders();
      const res = await fetch(`${apiBase()}/v1/repos/${repoId}/findings/${fid}`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({
          status: "dismissed",
          reason: dismissReason.trim() || undefined,
        }),
      });
      const text = await res.text();
      if (!res.ok) {
        setMessage(text || `Request failed (${res.status})`);
        return;
      }
      setDismissOpen(false);
      setDismissReason("");
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
      {links.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-2 text-xs">
          {links.map((l, i) =>
            l.url ? (
              <a key={i} href={l.url} className="font-medium text-primary hover:underline">
                {l.label ?? "Link"}
              </a>
            ) : null,
          )}
        </div>
      ) : null}
      {caveats.length > 0 ? (
        <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-muted-foreground">
          {caveats.map((c, i) => (
            <li key={i}>{typeof c === "string" ? c : JSON.stringify(c)}</li>
          ))}
        </ul>
      ) : null}
      <details className="mt-2 rounded-md border border-dashed border-border bg-muted/20 p-2 text-xs">
        <summary className="cursor-pointer font-medium text-muted-foreground">Technical detail</summary>
        <div className="mt-2 space-y-1 font-mono text-[11px]">
          {witnessNodes.length > 0 ? (
            <div>
              <span className="text-muted-foreground">Witness nodes: </span>
              {witnessNodes.join(", ")}
            </div>
          ) : rawNodes.length > 0 ? (
            <div>
              <span className="text-muted-foreground">Witness nodes: </span>
              {rawNodes.map((n) => String(n)).join(", ")}
            </div>
          ) : (
            <span className="text-muted-foreground">No witness node ids.</span>
          )}
        </div>
      </details>
      {fid && status !== "dismissed" ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" disabled={busy !== null} onClick={() => setDismissOpen(true)}>
            {busy === "dismiss" ? "…" : "Dismiss…"}
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

      <Dialog open={dismissOpen} onOpenChange={setDismissOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Dismiss finding</DialogTitle>
            <DialogDescription>
              This records an audit entry on the finding. You can add an optional reason for your team.
            </DialogDescription>
          </DialogHeader>
          <label className="grid gap-1 text-sm">
            <span className="text-muted-foreground">Reason (optional)</span>
            <textarea
              className="min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={dismissReason}
              onChange={(e) => setDismissReason(e.target.value)}
              placeholder="e.g. accepted risk for this release"
            />
          </label>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button type="button" variant="outline" onClick={() => setDismissOpen(false)}>
              Cancel
            </Button>
            <Button type="button" disabled={busy === "dismiss"} onClick={() => void dismissConfirm()}>
              Confirm dismiss
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
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
