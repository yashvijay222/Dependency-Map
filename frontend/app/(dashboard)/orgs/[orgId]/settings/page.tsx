import Link from "next/link";

import { Card, CardContent } from "@/components/ui/card";
import { isValidUuid } from "@/lib/uuid";

import { OrgSettingsForm } from "./org-settings-form";

export default async function OrgSettingsPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  if (!isValidUuid(orgId)) {
    return (
      <main className="mx-auto max-w-lg px-4 py-8 md:px-8">
        <Card>
          <CardContent className="pt-6 text-sm">Use a real organization UUID from your workspace.</CardContent>
        </Card>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-lg px-4 py-8 md:px-8">
      <h1 className="text-2xl font-semibold tracking-tight">Organization caps</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Owner or admin only. Values merge into <code className="text-xs">organizations.settings</code> on the API.
      </p>

      <OrgSettingsForm orgId={orgId} />

      <p className="mt-6 text-sm">
        <Link href={`/orgs/${orgId}/eval`} className="text-primary hover:underline">
          Finding review summary
        </Link>
      </p>
    </main>
  );
}
