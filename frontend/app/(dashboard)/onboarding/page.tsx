import Link from "next/link";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const steps = [
  {
    title: "Install the GitHub App",
    body: "Add the Dependency Map GitHub App to your org or account so we can read PR metadata and clone with installation tokens.",
  },
  {
    title: "Register repositories",
    body: "From the dashboard, open your organization and confirm linked repositories appear under Repositories.",
  },
  {
    title: "Enable contract analysis",
    body: "In organization settings JSON (or caps UI), set cpg_contract_analysis and optional finding_suppressions when you are ready for noise control.",
  },
  {
    title: "Open a test PR",
    body: "Push a branch and open a pull request; the webhook should enqueue an analysis. Open the PR timeline in the app to compare runs.",
  },
];

export default function OnboardingPage() {
  return (
    <main className="mx-auto max-w-2xl px-4 py-8 md:px-8">
      <h1 className="text-2xl font-semibold tracking-tight">Onboarding</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Checklist to go from empty workspace to first pre-merge contract run.
      </p>

      <ol className="mt-8 space-y-4">
        {steps.map((s, i) => (
          <li key={s.title}>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Step {i + 1}</CardDescription>
                <CardTitle className="text-base">{s.title}</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">{s.body}</CardContent>
            </Card>
          </li>
        ))}
      </ol>

      <p className="mt-10 text-sm">
        <Link href="/dashboard" className="font-medium text-primary hover:underline">
          Back to dashboard
        </Link>
      </p>
    </main>
  );
}
