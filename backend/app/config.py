from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Monorepo: shared secrets live in repo-root `.env`; optional `backend/.env` overrides.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(_REPO_ROOT / ".env"),
            str(_BACKEND_DIR / ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_base_url: str = "http://localhost:3000"
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    github_webhook_secret: str = ""
    github_app_id: str = ""
    github_app_private_key: str = ""
    redis_url: str = "redis://localhost:6379/0"
    use_celery: bool = False
    api_key_pepper: str = "change-me-in-production"
    cors_origins: str = "http://localhost:3000"

    # Cross-repo / worker tuning (org.settings JSON can override per-org in code paths)
    max_consumer_repos: int = 20
    snapshot_batch_size: int = 5
    drift_check_max_branches_per_repo: int = 8
    super_graph_max_nodes: int = 50_000
    github_max_retries: int = 5
    openai_api_key: str = ""
    analysis_artifact_bucket: str = "analysis-artifacts"
    analysis_signed_url_ttl_seconds: int = 600
    enable_cpg_bridge: bool = True
    focused_contract_scan_max_changed_files: int = 15

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
