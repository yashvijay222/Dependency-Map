"use client";

import { FolderGit2, LayoutDashboard, Radar, Settings2 } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

const links = [
  { id: "dashboard", href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  {
    id: "this-repo",
    href: "/repos/this-repo",
    label: "This repo",
    icon: FolderGit2,
  },
  { href: "/drift", label: "Drift monitor", icon: Radar, disabled: true },
  { href: "/settings", label: "Settings", icon: Settings2, disabled: true },
];

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-56 shrink-0 border-r border-border bg-card/50 md:flex md:flex-col">
      <div className="flex h-14 items-center border-b border-border px-4">
        <Link href="/dashboard" className="text-sm font-semibold tracking-tight">
          Dependency Map
        </Link>
      </div>
      <nav className="flex flex-1 flex-col gap-1 p-2">
        {links.map(({ id, href, label, icon: Icon, disabled }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Button
              key={id ?? href}
              variant={active ? "secondary" : "ghost"}
              className={cn("justify-start gap-2", disabled && "opacity-50")}
              disabled={disabled}
              asChild={!disabled}
            >
              {disabled ? (
                <span>
                  <Icon className="size-4" />
                  {label}
                </span>
              ) : (
                <Link href={href}>
                  <Icon className="size-4" />
                  {label}
                </Link>
              )}
            </Button>
          );
        })}
      </nav>
      <Separator />
      <p className="p-4 text-xs text-muted-foreground">v0.1 · MVP</p>
    </aside>
  );
}
