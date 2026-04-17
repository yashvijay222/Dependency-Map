# Environments and staging matrix

Use this matrix when deploying Dependency Map beyond local development.

| Variable / surface | Local dev | Staging | Production |
|---------------------|-----------|----------|------------|
| `SUPABASE_URL` | Dev project | **Dedicated staging project** | Production project |
| `SUPABASE_SERVICE_ROLE_KEY` | Staging key | Staging key | Prod key (rotation policy) |
| GitHub App | Optional; can use staging app installation | **Staging GitHub App** on a test org | Production app |
| `GITHUB_WEBHOOK_SECRET` | Dev secret | Staging secret | Unique per env |
| `NEXT_PUBLIC_*` | Points to local API | Staging API URL | Production API URL |
| `USE_CELERY` | Often `false` | `true` with Redis | `true` with HA Redis |
| `REDIS_URL` | Local Redis | Staging Redis | Managed Redis |
| Feature flags ([backend/app/config.py](backend/app/config.py)) | All toggles as needed | Enable incrementally (e.g. `feature_github_check_runs`) | Enable after validation |

## Observability (Phase 0)

- Configure log aggregation to parse JSON lines from logger `dm.pipeline` (see [backend/app/observability.py](backend/app/observability.py)).
- Poll `GET /health/metrics` for in-process counters (`analysis_started`, `analysis_completed`, etc.) until Prometheus/OpenTelemetry is wired.

## CI

GitHub Actions runs lint, tests, and CPG smoke against the repo checkout—**not** against live Supabase. Use staging for integration tests that need real PostgREST.
