# Dependency Map

Monorepo for the Dependency Map OS MVP: **Next.js** (`frontend/`), **FastAPI** (`backend/`), and **Supabase** (SQL in `supabase/migrations`).

## Prerequisites

- Node 20+
- [uv](https://docs.astral.sh/uv/) (Python 3.11+)
- A Supabase project (Auth + Postgres)

## Environment

All variables are documented in **`.env.example`** at the repo root.

- Copy the **Frontend** section into **`frontend/.env.local`** (anon key and `NEXT_PUBLIC_*` only; never the service role).
- Copy the **Backend** section into **`backend/.env`**.

Apply migrations in the Supabase SQL editor or via `supabase db push` when using the Supabase CLI.

## Run locally

**API**

```bash
cd backend
uv sync --extra dev
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Web**

```bash
npm install
cd frontend && npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Protected routes: `/dashboard`, `/orgs/...`, `/repos/...`.

## CI

From the repo root: `npm install`, `npm run lint`, `npm run build` (web); `cd backend && uv sync --extra dev && uv run ruff check app` (API).
