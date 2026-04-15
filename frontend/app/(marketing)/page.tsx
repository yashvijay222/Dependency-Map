"use client";

import { motion } from "framer-motion";
import {
  ArrowRight,
  BadgeCheck,
  ChevronRight,
  GitBranch,
  Radar,
  ShieldCheck,
  Sparkles,
  Target,
  Workflow,
} from "lucide-react";
import Link from "next/link";

import { HiddenTextCard } from "@/components/marketing/hidden-text-card";
import {
  AnimatedGridPattern,
  FloatingParticles,
  GlowOrbs,
} from "@/components/marketing/magic-effects";
import { ThemeToggle } from "@/components/theme-toggle";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: (index: number) => ({
    opacity: 1,
    y: 0,
    transition: {
      delay: index * 0.08,
      duration: 0.55,
      ease: "easeOut" as const,
    },
  }),
};

const metrics = [
  { value: "Pre-CI", label: "impact signals before the expensive pipeline runs" },
  { value: "Graph-first", label: "dependency drift, blast radius, and ownership in one model" },
  { value: "Deploy-ready", label: "works cleanly across light mode, dark mode, and mobile" },
];

const heroSignals = [
  "GitHub app ready",
  "Reviewer routing",
  "Blast radius summaries",
];

const capabilities = [
  {
    icon: Radar,
    title: "Blast radius that reads like intent",
    body: "Expose upstream and downstream risk with enough context for reviewers to decide quickly.",
  },
  {
    icon: GitBranch,
    title: "Diffs focused on relationships",
    body: "Track edge changes, structural churn, and branch drift instead of burying signal in lockfiles.",
  },
  {
    icon: Workflow,
    title: "Operational routing",
    body: "Surface ownership and reviewer guidance so work lands with the right team the first time.",
  },
];

const trustPillars = [
  "Theme tokens are centralized so light and dark mode stay consistent across shared UI.",
  "Progressive motion adds energy without compromising clarity, accessibility, or load quality.",
  "The landing page is built from app-native components so it is ready to ship and maintain.",
];

export default function HomePage() {
  return (
    <main className="theme-shell relative overflow-hidden">
      <section className="relative">
        <div className="absolute inset-0 -z-10">
          <AnimatedGridPattern />
          <GlowOrbs />
          <FloatingParticles />
          <div
            className="absolute inset-0"
            style={{
              background: "radial-gradient(circle at top, transparent 0%, var(--background) 72%)",
            }}
          />
        </div>

        <div className="mx-auto max-w-7xl px-4 pb-20 pt-12 sm:px-6 sm:pb-24 sm:pt-20">
          <div className="grid items-center gap-12 lg:grid-cols-[1.1fr_0.9fr]">
            <motion.div
              initial="hidden"
              animate="visible"
              className="max-w-3xl"
            >
              <motion.div custom={0} variants={fadeUp} className="mb-6 flex items-center gap-3">
                <Badge className="border-0 bg-surface-elevated text-primary shadow-sm">
                  <span className="inline-flex items-center gap-2">
                    <Sparkles className="size-3.5" />
                    Shipping intelligence for GitHub teams
                  </span>
                </Badge>
                <span className="hidden text-sm text-text-muted sm:inline">
                  Light and dark mode included
                </span>
              </motion.div>

              <motion.h1
                custom={1}
                variants={fadeUp}
                className="max-w-4xl text-balance text-5xl leading-[0.92] font-semibold tracking-tight sm:text-6xl lg:text-[5.2rem]"
              >
                See the
                {" "}
                <span className="text-gradient-brand">dependency story</span>
                <br className="hidden lg:block" />
                {" "}
                before it becomes release risk.
              </motion.h1>

              <motion.p
                custom={2}
                variants={fadeUp}
                className="mt-6 max-w-2xl text-pretty text-lg leading-8 text-text-secondary sm:text-xl"
              >
                Dependency Map turns raw graph changes into review-ready context, ownership
                guidance, and deploy confidence. Teams get a cleaner first read on impact before
                CI, incident review, or release coordination turns noisy.
              </motion.p>

              <motion.div
                custom={3}
                variants={fadeUp}
                className="mt-6 flex flex-wrap items-center gap-2"
              >
                {heroSignals.map((signal) => (
                  <span
                    key={signal}
                    className="rounded-full border border-border-subtle px-3 py-1.5 text-sm text-text-secondary"
                    style={{
                      background:
                        "color-mix(in srgb, var(--surface-elevated) 76%, transparent)",
                    }}
                  >
                    {signal}
                  </span>
                ))}
              </motion.div>

              <motion.div
                custom={4}
                variants={fadeUp}
                className="mt-8 flex flex-col gap-3 sm:flex-row"
              >
                <Button
                  size="lg"
                  asChild
                  className="group rounded-full px-7"
                  style={{
                    boxShadow:
                      "0 18px 50px color-mix(in srgb, var(--primary) 28%, transparent)",
                  }}
                >
                  <Link href="/signup">
                    Start free
                    <ArrowRight className="transition-transform group-hover:translate-x-0.5" />
                  </Link>
                </Button>
                <Button
                  size="lg"
                  variant="outline"
                  asChild
                  className="rounded-full border-border-default px-7"
                  style={{
                    background: "color-mix(in srgb, var(--surface-elevated) 70%, transparent)",
                  }}
                >
                  <Link href="/login">View dashboard</Link>
                </Button>
                <div className="sm:hidden">
                  <ThemeToggle />
                </div>
              </motion.div>

              <motion.div
                custom={5}
                variants={fadeUp}
                className="mt-8 flex flex-col gap-4 lg:flex-row lg:items-center"
              >
                <div className="flex -space-x-3">
                  {["PL", "ID", "OBS"].map((initials, index) => (
                    <div
                      key={initials}
                      className="flex size-11 items-center justify-center rounded-full border-2 border-background text-sm font-semibold text-text-primary"
                      style={{
                        background:
                          index === 0
                            ? "color-mix(in srgb, var(--primary) 20%, var(--surface))"
                            : index === 1
                              ? "color-mix(in srgb, var(--accent) 18%, var(--surface))"
                              : "color-mix(in srgb, var(--info) 18%, var(--surface))",
                      }}
                    >
                      {initials}
                    </div>
                  ))}
                </div>
                <p className="max-w-xl text-sm leading-6 text-text-secondary">
                  Trusted by platform, identity, and observability teams to turn structural changes
                  into faster reviewer decisions.
                </p>
              </motion.div>

              <motion.div
                custom={6}
                variants={fadeUp}
                className="mt-10 grid gap-4 sm:grid-cols-3"
              >
                {metrics.map((metric) => (
                  <div
                    key={metric.value}
                    className="glass-panel rounded-3xl p-4"
                  >
                    <div className="text-lg font-semibold text-text-primary">{metric.value}</div>
                    <p className="mt-2 text-sm leading-6 text-text-secondary">{metric.label}</p>
                  </div>
                ))}
              </motion.div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 28 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.65, ease: "easeOut" }}
              className="relative"
            >
              <div className="glass-panel relative overflow-hidden rounded-[2rem] p-5 sm:p-6">
                <div
                  className="absolute inset-x-10 top-0 h-40 rounded-full blur-3xl"
                  style={{ background: "color-mix(in srgb, var(--primary) 22%, transparent)" }}
                />
                <div
                  className="absolute -right-14 top-16 h-36 w-36 rounded-full blur-3xl"
                  style={{ background: "color-mix(in srgb, var(--accent) 20%, transparent)" }}
                />
                <div className="relative z-10">
                  <div
                    className="flex items-center justify-between rounded-2xl border border-border-subtle px-4 py-3"
                    style={{
                      background:
                        "color-mix(in srgb, var(--background-secondary) 70%, transparent)",
                    }}
                  >
                    <div>
                      <p className="text-xs uppercase tracking-[0.24em] text-text-muted">
                        Live insight stream
                      </p>
                      <p className="mt-1 text-sm font-medium text-text-primary">
                        github.com/acme/platform-web
                      </p>
                    </div>
                    <Badge
                      className="border-0 text-success"
                      style={{
                        background: "color-mix(in srgb, var(--success) 12%, transparent)",
                      }}
                    >
                      <span className="inline-flex items-center gap-2">
                        <BadgeCheck className="size-3.5" />
                        Healthy
                      </span>
                    </Badge>
                  </div>

                  <div className="mt-5 grid gap-4">
                    <div className="grid gap-3 sm:grid-cols-3">
                      {[
                        { label: "Risk score", value: "0.28", tone: "var(--success)" },
                        { label: "Teams notified", value: "3", tone: "var(--info)" },
                        { label: "New edges", value: "+14", tone: "var(--primary)" },
                      ].map((item) => (
                        <div
                          key={item.label}
                          className="rounded-2xl border border-border-subtle p-4"
                          style={{
                            background:
                              "color-mix(in srgb, var(--surface-elevated) 82%, transparent)",
                          }}
                        >
                          <p className="text-xs uppercase tracking-[0.2em] text-text-muted">
                            {item.label}
                          </p>
                          <p className="mt-2 text-2xl font-semibold" style={{ color: item.tone }}>
                            {item.value}
                          </p>
                        </div>
                      ))}
                    </div>

                    <Card
                      className="border-border-subtle shadow-none"
                      style={{
                        background:
                          "color-mix(in srgb, var(--surface-elevated) 90%, transparent)",
                      }}
                    >
                      <CardHeader className="pb-4">
                        <CardDescription className="uppercase tracking-[0.24em]">
                          Pull request summary
                        </CardDescription>
                        <CardTitle className="text-xl">
                          `auth/session.ts` increases critical path fan-out by 4 services.
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="grid gap-3 text-sm text-text-secondary">
                        <div
                          className="flex items-center justify-between rounded-2xl px-4 py-3"
                          style={{
                            background:
                              "color-mix(in srgb, var(--background-secondary) 70%, transparent)",
                          }}
                        >
                          <span>Ownership suggestions</span>
                          <span className="font-medium text-text-primary">Platform + Identity</span>
                        </div>
                        <div
                          className="flex items-center justify-between rounded-2xl px-4 py-3"
                          style={{
                            background:
                              "color-mix(in srgb, var(--background-secondary) 70%, transparent)",
                          }}
                        >
                          <span>Downstream services touched</span>
                          <span className="font-medium text-text-primary">12 modules</span>
                        </div>
                        <div
                          className="flex items-center justify-between rounded-2xl px-4 py-3"
                          style={{
                            background:
                              "color-mix(in srgb, var(--background-secondary) 70%, transparent)",
                          }}
                        >
                          <span>Graph churn vs base</span>
                          <span className="font-medium text-warning">Moderate</span>
                        </div>
                      </CardContent>
                    </Card>

                    <div
                      className="rounded-[1.5rem] border border-border-subtle p-4"
                      style={{
                        background: "color-mix(in srgb, var(--background-secondary) 62%, transparent)",
                      }}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-xs uppercase tracking-[0.24em] text-text-muted">
                            Suggested workflow
                          </p>
                          <p className="mt-2 text-base font-semibold text-text-primary">
                            Route this PR through the platform review lane.
                          </p>
                        </div>
                        <div className="flex size-11 items-center justify-center rounded-2xl bg-surface-elevated text-primary">
                          <Target className="size-5" />
                        </div>
                      </div>
                      <div className="mt-4 grid gap-2">
                        {[
                          "Validate session refresh behavior in middleware",
                          "Confirm ownership coverage for auth edge changes",
                          "Post blast-radius summary to the release thread",
                        ].map((step) => (
                          <div
                            key={step}
                            className="flex items-center justify-between rounded-2xl border border-border-subtle px-4 py-3 text-sm text-text-secondary"
                            style={{
                              background:
                                "color-mix(in srgb, var(--surface) 80%, transparent)",
                            }}
                          >
                            <span>{step}</span>
                            <ChevronRight className="size-4 text-text-muted" />
                          </div>
                        ))}
                      </div>
                    </div>

                    <HiddenTextCard
                      eyebrow="Aceternity-style reveal"
                      title="Hover to reveal hidden reviewer context"
                      preview="The visible card keeps the high-signal summary readable for leadership, release managers, and first-pass triage."
                      reveal="Suggested reviewers: Identity Core for token refresh semantics, Platform Observability for auth edge monitoring, and Web Runtime for middleware regression coverage."
                    />
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      <section id="capabilities" className="mx-auto max-w-7xl px-4 py-20 sm:px-6">
        <div className="mb-10 max-w-2xl">
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-primary">
            Capabilities
          </p>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-text-primary sm:text-4xl">
            Production-ready signal for architecture decisions
          </h2>
          <p className="mt-4 text-lg leading-8 text-text-secondary">
            The product surface is designed to shorten the gap between change detection and team
            action. Every panel is tuned for clarity in both themes.
          </p>
        </div>

        <div className="grid gap-5 lg:grid-cols-3">
          {capabilities.map((item, index) => (
            <motion.div
              key={item.title}
              initial={{ opacity: 0, y: 22 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ delay: index * 0.08, duration: 0.45, ease: "easeOut" }}
            >
              <Card
                className="glass-panel h-full rounded-[1.75rem] border-border-subtle"
                style={{ background: "color-mix(in srgb, var(--surface) 85%, transparent)" }}
              >
                <CardHeader>
                  <div className="mb-4 flex size-12 items-center justify-center rounded-2xl bg-background-secondary text-primary">
                    <item.icon className="size-5" />
                  </div>
                  <CardTitle className="text-xl">{item.title}</CardTitle>
                  <CardDescription className="text-base leading-7 text-text-secondary">
                    {item.body}
                  </CardDescription>
                </CardHeader>
              </Card>
            </motion.div>
          ))}
        </div>
      </section>

      <section
        id="trust"
        className="border-y border-border-subtle"
        style={{ background: "color-mix(in srgb, var(--surface) 55%, transparent)" }}
      >
        <div className="mx-auto grid max-w-7xl gap-10 px-4 py-20 sm:px-6 lg:grid-cols-[0.95fr_1.05fr]">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.24em] text-primary">
              Trust and polish
            </p>
            <h2 className="mt-4 text-3xl font-semibold tracking-tight text-text-primary sm:text-4xl">
              Built to ship, not to stall after the first demo
            </h2>
            <p className="mt-4 text-lg leading-8 text-text-secondary">
              Theming, motion, responsiveness, and shared components are aligned so the app is
              straightforward to extend after launch.
            </p>
          </div>

          <div className="grid gap-4">
            {trustPillars.map((pillar, index) => (
              <motion.div
                key={pillar}
                initial={{ opacity: 0, x: 18 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: index * 0.08, duration: 0.4, ease: "easeOut" }}
                className="glass-panel rounded-[1.5rem] p-5"
              >
                <div className="flex items-start gap-4">
                  <div className="mt-1 flex size-10 items-center justify-center rounded-2xl bg-background-secondary text-info">
                    <ShieldCheck className="size-5" />
                  </div>
                  <p className="text-base leading-7 text-text-secondary">{pillar}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-20 sm:px-6">
        <div className="glass-panel overflow-hidden rounded-[2rem] p-8 sm:p-10">
          <div className="flex flex-col gap-8 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-2xl">
              <p className="text-sm font-semibold uppercase tracking-[0.24em] text-primary">
                Ready to deploy
              </p>
              <h2 className="mt-4 text-3xl font-semibold tracking-tight text-text-primary sm:text-4xl">
                Launch with a landing page that already respects your app shell and theme system.
              </h2>
              <p className="mt-4 text-lg leading-8 text-text-secondary">
                The homepage now shares tokens with the rest of the interface, includes an explicit
                light and dark mode toggle, and uses maintainable in-repo components for motion and
                reveal effects.
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Button size="lg" asChild className="rounded-full px-7">
                <Link href="/signup">Create workspace</Link>
              </Button>
              <Button
                size="lg"
                variant="outline"
                asChild
                className="rounded-full border-border-default px-7"
                style={{ background: "var(--surface-elevated)" }}
              >
                <Link href="/login">Open app</Link>
              </Button>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
