# Service level objectives (internal)

Targets for hosted analysis (Phase 6); measure using `/health/metrics` counters and log `dm.pipeline` events.

| Signal | Target (initial) | Notes |
|--------|------------------|-------|
| Analysis success rate | ≥ 95% weekly | `analysis_completed` / (`analysis_completed` + `analysis_failed`) |
| p95 wall time (standard mode) | under 5 minutes (median repo) | From `analysis_started` → `analysis_finished` duration in logs |
| GitHub 429 rate | Near zero bursts | `github_429` counter (incremented on each rate-limit response in `github_client`) |
| CPG mining wall time | Track p95 after baseline | `cpg_mining_ms_total` / `cpg_mining_runs` from `/health/metrics` plus `dm.pipeline` `cpg_mining_finished.duration_ms` |

Tune thresholds per customer tier after baseline data exists.
