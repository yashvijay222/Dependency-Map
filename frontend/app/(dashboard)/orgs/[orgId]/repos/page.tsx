import Link from "next/link";
import { apiFetchOptional } from "@/lib/api";
import { isValidUuid } from "@/lib/uuid";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default async function OrgReposPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  const repos = isValidUuid(orgId)
    ? await apiFetchOptional(`/v1/orgs/${orgId}/repositories`)
    : {
        ok: false as const,
        error:
          "This page needs a real organization UUID from the database. Open it from the dashboard after your org loads.",
      };

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 md:px-8">
      <h1 className="text-2xl font-semibold tracking-tight">Repositories</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Organization{" "}
        <code className="rounded-md border border-border bg-muted px-1.5 py-0.5 text-xs">
          {orgId}
        </code>
      </p>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Linked repos</CardTitle>
          <CardDescription>
            Populated from the API when org/repo sync is enabled.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {repos.ok &&
          repos.data &&
          typeof repos.data === "object" &&
          repos.data !== null &&
          "repositories" in repos.data &&
          Array.isArray((repos.data as { repositories: unknown }).repositories) ? (
            <ul className="divide-y divide-border rounded-lg border border-border">
              {(repos.data as { repositories: { full_name?: string; id?: string }[] }).repositories.map(
                (r) => (
                  <li key={r.id ?? r.full_name} className="px-4 py-3 text-sm">
                    <Link
                      href={`/repos/${r.id}`}
                      className="font-medium text-primary hover:underline"
                    >
                      {r.full_name ?? r.id}
                    </Link>
                  </li>
                ),
              )}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              {repos.ok
                ? "No repositories in response yet."
                : (repos.error ??
                  "Repos listing requires GET /v1/orgs/{id}/repositories on the API.")}
            </p>
          )}
        </CardContent>
      </Card>

      <Link href="/dashboard" className="mt-8 inline-block text-sm font-medium text-primary hover:underline">
        Back to dashboard
      </Link>
    </main>
  );
}
