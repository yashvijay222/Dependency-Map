"""Celery app for analysis workers."""

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "dependency_map",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_default_queue="celery",
    task_routes={
        "dm.snapshot_repo_branch": {"queue": "snapshot"},
        "dm.build_org_graph": {"queue": "snapshot"},
        "dm.compute_branch_drift": {"queue": "snapshot"},
        "dm.enqueue_org_snapshots": {"queue": "snapshot"},
        "dm.enqueue_all_org_snapshots": {"queue": "snapshot"},
        "dm.enqueue_org_drift_checks": {"queue": "snapshot"},
        "dm.enqueue_all_org_drift_checks": {"queue": "snapshot"},
        "dm.cleanup_deleted_branch": {"queue": "snapshot"},
        "dm.run_ml_train": {"queue": "ml"},
        "dm.run_cpg_contract_score": {"queue": "celery"},
    },
)

celery_app.conf.beat_schedule = {
    "enqueue-all-org-snapshots-6h": {
        "task": "dm.enqueue_all_org_snapshots",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    "backfill-schema-version-weekly": {
        "task": "dm.backfill_schema_versions",
        "schedule": crontab(minute=15, hour=3, day_of_week=0),
    },
    "drift-check-org-round-12h": {
        "task": "dm.enqueue_all_org_drift_checks",
        "schedule": crontab(minute=45, hour="*/12"),
    },
    "nightly-ml-training": {
        "task": "dm.enqueue_all_org_ml_training",
        "schedule": crontab(minute=0, hour=2),
    },
}


@celery_app.task(name="dm.run_analysis")
def run_analysis_task(analysis_id: str) -> None:
    from app.worker.tasks import run_analysis_job

    run_analysis_job(analysis_id)


@celery_app.task(name="dm.snapshot_repo_branch")
def snapshot_repo_branch_task(repo_id: str, branch: str, sha: str | None = None) -> None:
    from app.worker.cross_repo_tasks import snapshot_repo_branch

    snapshot_repo_branch(repo_id, branch, sha)


@celery_app.task(name="dm.build_org_graph")
def build_org_graph_task(org_id: str, branch: str | None = None) -> None:
    from app.worker.cross_repo_tasks import build_org_graph

    build_org_graph(org_id, branch)


@celery_app.task(name="dm.compute_branch_drift")
def compute_branch_drift_task(repo_id: str, branch_a: str, branch_b: str) -> None:
    from app.worker.cross_repo_tasks import compute_branch_drift

    compute_branch_drift(repo_id, branch_a, branch_b)


@celery_app.task(name="dm.enqueue_org_snapshots")
def enqueue_org_snapshots_task(org_id: str) -> None:
    from app.worker.cross_repo_tasks import enqueue_org_snapshots

    enqueue_org_snapshots(org_id)


@celery_app.task(name="dm.enqueue_org_drift_checks")
def enqueue_org_drift_checks_task(org_id: str) -> None:
    from app.worker.cross_repo_tasks import enqueue_org_drift_checks

    enqueue_org_drift_checks(org_id)


@celery_app.task(name="dm.enqueue_all_org_drift_checks")
def enqueue_all_org_drift_checks_task() -> None:
    from supabase import create_client

    from app.worker.cross_repo_tasks import _org_jitter_seconds

    if not settings.supabase_url or not settings.supabase_service_role_key:
        return
    sb = create_client(settings.supabase_url, settings.supabase_service_role_key)
    ores = sb.table("organizations").select("id").execute()
    for row in ores.data or []:
        oid = str(row["id"])
        countdown = _org_jitter_seconds(oid + ":drift", modulo=600)
        enqueue_org_drift_checks_task.apply_async(args=[oid], countdown=countdown)


@celery_app.task(name="dm.cleanup_deleted_branch")
def cleanup_deleted_branch_task(repo_id: str, branch: str) -> None:
    from app.worker.cross_repo_tasks import cleanup_deleted_branch

    cleanup_deleted_branch(repo_id, branch)


@celery_app.task(name="dm.enqueue_all_org_snapshots")
def enqueue_all_org_snapshots_task() -> None:
    from supabase import create_client

    from app.config import settings
    from app.worker.cross_repo_tasks import _org_jitter_seconds

    if not settings.supabase_url or not settings.supabase_service_role_key:
        return
    sb = create_client(settings.supabase_url, settings.supabase_service_role_key)
    ores = sb.table("organizations").select("id").execute()
    for row in ores.data or []:
        oid = str(row["id"])
        countdown = _org_jitter_seconds(oid, modulo=300)
        enqueue_org_snapshots_task.apply_async(args=[oid], countdown=countdown)


@celery_app.task(name="dm.backfill_schema_versions")
def backfill_schema_versions_task() -> None:
    from app.worker.cross_repo_tasks import backfill_pr_analysis_schema_versions

    backfill_pr_analysis_schema_versions()


@celery_app.task(name="dm.run_ml_train")
def run_ml_train_task(org_id: str) -> None:
    from app.worker.ml_tasks import train_org_model

    train_org_model(org_id)


@celery_app.task(name="dm.run_cpg_contract_score")
def run_cpg_contract_score_task(repo_root: str, out_dir: str, base: str, head: str) -> dict:
    """Run offline CPG invariant scorer on a worker-local checkout (see ``cpg_contract_tasks``)."""

    from app.worker.cpg_contract_tasks import run_cpg_contract_score_sync

    return run_cpg_contract_score_sync(repo_root, out_dir, base, head)


@celery_app.task(name="dm.enqueue_all_org_ml_training")
def enqueue_all_org_ml_training_task() -> None:
    from supabase import create_client

    from app.worker.cross_repo_tasks import _org_jitter_seconds

    if not settings.supabase_url or not settings.supabase_service_role_key:
        return
    sb = create_client(settings.supabase_url, settings.supabase_service_role_key)
    ores = sb.table("organizations").select("id").execute()
    for row in ores.data or []:
        oid = str(row["id"])
        countdown = _org_jitter_seconds(oid + ":ml", modulo=900)
        run_ml_train_task.apply_async(args=[oid], countdown=countdown)
