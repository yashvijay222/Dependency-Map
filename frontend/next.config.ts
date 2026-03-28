import path from "path";
import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const monorepoRoot = path.join(__dirname, "..");
const isDev = process.env.NODE_ENV !== "production";

// Next (and any prior `loadEnvConfig`) caches env. Without `forceReload`, a later
// `loadEnvConfig(monorepoRoot)` can return that cache and never read repo-root `.env`.
// Use repo-root `.env`, `.env.local`, `.env.development`, etc. (`isDev` picks the right set).
loadEnvConfig(monorepoRoot, isDev, console, true);

const nextConfig: NextConfig = {
  // Monorepo: trace files from repo root when parent lockfiles exist
  outputFileTracingRoot: monorepoRoot,
};

export default nextConfig;
