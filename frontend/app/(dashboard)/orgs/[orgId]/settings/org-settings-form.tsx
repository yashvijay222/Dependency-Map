"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiBase } from "@/lib/api-base";
import { createClient } from "@/lib/supabase/client";

export function OrgSettingsForm({ orgId }: { orgId: string }) {
  const router = useRouter();
  const [maxConsumers, setMaxConsumers] = useState("");
  const [maxPacks, setMaxPacks] = useState("");
  const [tokenBudget, setTokenBudget] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setMessage(null);
    try {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session?.access_token) {
        setMessage("Sign in to update organization settings.");
        return;
      }
      const body: { settings: Record<string, unknown> } = { settings: {} };
      if (maxConsumers.trim()) {
        body.settings.max_consumer_repos = Number.parseInt(maxConsumers, 10);
      }
      if (maxPacks.trim()) {
        body.settings.reasoner_max_packs_per_run = Number.parseInt(maxPacks, 10);
      }
      if (tokenBudget.trim()) {
        body.settings.reasoner_monthly_token_budget = Number.parseInt(tokenBudget, 10);
      }
      if (Object.keys(body.settings).length === 0) {
        setMessage("Enter at least one value.");
        return;
      }
      const res = await fetch(`${apiBase()}/v1/orgs/${orgId}/settings`, {
        method: "PATCH",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify(body),
      });
      const text = await res.text();
      if (!res.ok) {
        setMessage(text || `HTTP ${res.status}`);
        return;
      }
      setMessage("Saved.");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Limits</CardTitle>
          <CardDescription>Optional integers; leave blank to skip.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="max_consumer_repos">
              max_consumer_repos
            </label>
            <Input
              id="max_consumer_repos"
              inputMode="numeric"
              placeholder="e.g. 25"
              value={maxConsumers}
              onChange={(e) => setMaxConsumers(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="reasoner_max_packs">
              reasoner_max_packs_per_run
            </label>
            <Input
              id="reasoner_max_packs"
              inputMode="numeric"
              placeholder="e.g. 20"
              value={maxPacks}
              onChange={(e) => setMaxPacks(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="reasoner_monthly_token_budget">
              reasoner_monthly_token_budget
            </label>
            <Input
              id="reasoner_monthly_token_budget"
              inputMode="numeric"
              placeholder="e.g. 5000000"
              value={tokenBudget}
              onChange={(e) => setTokenBudget(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">Monthly cap for reasoner tokens across the org.</p>
          </div>
          <Button type="button" disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Save"}
          </Button>
          {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
        </CardContent>
      </Card>

      <div className="mt-8 flex flex-wrap gap-4 text-sm">
        <Link href={`/orgs/${orgId}/repos`} className="text-primary hover:underline">
          Repositories
        </Link>
        <Link href="/dashboard" className="text-primary hover:underline">
          Dashboard
        </Link>
      </div>
    </>
  );
}
