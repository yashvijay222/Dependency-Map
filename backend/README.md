# Dependency Map API

FastAPI service for GitHub integration, analysis jobs, and pre-CI endpoints.

## Run locally

Copy the **Backend** section from the repo root **`.env.example`** into **`backend/.env`**, then:

```bash
cd backend
uv sync --extra dev
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health: `GET http://127.0.0.1:8000/health`
