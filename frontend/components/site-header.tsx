import Link from "next/link";
import { GitBranch, Radar, ShieldCheck } from "lucide-react";

import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border-subtle bg-background/72 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
        <Link
          href="/"
          className="flex items-center gap-3 text-sm font-semibold tracking-tight text-text-primary transition-opacity hover:opacity-90"
        >
          <span className="flex size-9 items-center justify-center rounded-2xl border border-border-subtle bg-surface-elevated shadow-sm">
            <GitBranch className="size-4 text-primary" />
          </span>
          <span className="flex flex-col leading-none">
            <span>Dependency Map</span>
            <span className="mt-1 text-[11px] font-medium uppercase tracking-[0.22em] text-text-muted">
              Pre-CI intelligence
            </span>
          </span>
        </Link>
        <nav className="flex items-center gap-1.5 sm:gap-2">
          <div className="hidden items-center gap-1 rounded-full border border-border-subtle bg-surface-elevated/80 p-1 md:flex">
            <Link
              href="/#capabilities"
              className="rounded-full px-3 py-2 text-sm text-text-secondary transition-colors hover:bg-background-secondary hover:text-text-primary"
            >
              <span className="inline-flex items-center gap-2">
                <Radar className="size-3.5" />
                Capabilities
              </span>
            </Link>
            <Link
              href="/#trust"
              className="rounded-full px-3 py-2 text-sm text-text-secondary transition-colors hover:bg-background-secondary hover:text-text-primary"
            >
              <span className="inline-flex items-center gap-2">
                <ShieldCheck className="size-3.5" />
                Trust
              </span>
            </Link>
          </div>
          <Button variant="ghost" size="sm" asChild className="text-text-secondary hover:text-text-primary">
            <Link href="/login">Log in</Link>
          </Button>
          <Button size="sm" asChild className="shadow-lg shadow-primary/15">
            <Link href="/signup">Sign up</Link>
          </Button>
          <ThemeToggle />
        </nav>
      </div>
    </header>
  );
}
