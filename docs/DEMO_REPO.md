# Demo repository (Phase 7)

Create a **public** demo repository that:

1. Contains a small **Next.js + FastAPI + Supabase** layout similar to Dependency Map itself.
2. Includes **intentional contract bugs** for each invariant family:
   - stale frontend `fetch` path vs renamed API route
   - migration dropping a table still referenced in a handler
   - Celery task name mismatch
3. Documents how to:
   - install the Dependency Map GitHub App on the demo org
   - open a PR and observe **CPG / contracts** output and (optionally) GitHub Checks

Link the demo repo URL from the main [README.md](../README.md) once published.
