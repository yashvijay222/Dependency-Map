import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status
from supabase import create_client

from app.config import settings
from app.worker.tasks import schedule_analysis_job

log = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/github", tags=["github"])


def _verify_github_signature(body: bytes, signature: str | None) -> bool:
    if not settings.github_webhook_secret or not signature:
        return False
    expected = "sha256=" + hmac.new(
        settings.github_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _sb():
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return None
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@router.post("/webhook")
async def github_webhook(
    request: Request,
    background: BackgroundTasks,
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
    x_github_event: str | None = Header(None, alias="X-GitHub-Event"),
    x_github_delivery: str | None = Header(None, alias="X-GitHub-Delivery"),
) -> dict[str, Any]:
    body = await request.body()
    if settings.github_webhook_secret and not _verify_github_signature(
        body,
        x_hub_signature_256,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return {"received": True, "queued": False, "reason": "invalid_json"}

    sb = _sb()
    if sb is None:
        return {"received": True, "queued": False, "reason": "supabase_not_configured"}

    event = x_github_event or ""

    if x_github_delivery:
        dup = (
            sb.table("github_webhook_deliveries")
            .select("delivery_id")
            .eq("delivery_id", x_github_delivery)
            .limit(1)
            .execute()
        )
        if dup.data:
            return {"received": True, "queued": False, "reason": "duplicate_delivery"}
        sb.table("github_webhook_deliveries").insert(
            {"delivery_id": x_github_delivery, "event_type": event or "unknown"},
        ).execute()

    if event == "pull_request":
        action = payload.get("action")
        if action not in ("opened", "synchronize", "reopened", "edited"):
            return {"received": True, "queued": False, "reason": f"action_{action}"}
        pr = payload.get("pull_request") or {}
        repo = payload.get("repository") or {}
        gh_repo_id = repo.get("id")
        if not gh_repo_id:
            return {"received": True, "queued": False, "reason": "no_repository"}
        rres = (
            sb.table("repositories")
            .select("id")
            .eq("github_repo_id", int(gh_repo_id))
            .limit(1)
            .execute()
        )
        if not rres.data:
            return {"received": True, "queued": False, "reason": "repo_not_registered"}
        repo_uuid = rres.data[0]["id"]
        base_sha = (pr.get("base") or {}).get("sha")
        head_sha = (pr.get("head") or {}).get("sha")
        pr_number = pr.get("number")
        if not base_sha or not head_sha:
            return {"received": True, "queued": False, "reason": "missing_shas"}
        row = {
            "repo_id": str(repo_uuid),
            "pr_number": pr_number,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "status": "pending",
            "summary_json": {},
            "github_pr_url": pr.get("html_url"),
        }
        # One row per (repo, PR, head): re-push updates the same analysis row.
        existing = (
            sb.table("pr_analyses")
            .select("id")
            .eq("repo_id", str(repo_uuid))
            .eq("pr_number", pr_number)
            .eq("head_sha", head_sha)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if existing.data:
            analysis_id = str(existing.data[0]["id"])
            sb.table("pr_analyses").update(
                {
                    "status": "pending",
                    "base_sha": base_sha,
                    "summary_json": {},
                    "github_pr_url": pr.get("html_url"),
                }
            ).eq("id", analysis_id).execute()
        else:
            ins = sb.table("pr_analyses").insert(row).execute()
            if not ins.data:
                return {"received": True, "queued": False, "reason": "insert_failed"}
            analysis_id = str(ins.data[0]["id"])
        schedule_analysis_job(analysis_id, background)
        return {"received": True, "queued": True, "analysis_id": analysis_id}

    if event == "installation":
        inst = payload.get("installation") or {}
        iid = inst.get("id")
        acct = (inst.get("account") or {}).get("login", "")
        action = payload.get("action")
        if action == "created" and iid:
            log.info("GitHub installation %s for %s — link org in app", iid, acct)
        return {"received": True, "queued": False, "event": "installation"}

    def _enqueue(task: str, args: list, countdown: int = 0) -> bool:
        try:
            from app.celery_app import celery_app

            celery_app.send_task(task, args=args, countdown=countdown)
            return True
        except Exception:
            log.exception("Celery enqueue %s failed; trying inline", task)
            return False

    if event == "push":
        repo_js = payload.get("repository") or {}
        gh_repo_id = repo_js.get("id")
        ref = str(payload.get("ref") or "")
        if not gh_repo_id or not ref.startswith("refs/heads/"):
            return {"received": True, "queued": False, "reason": "not_branch_push"}
        branch = ref.removeprefix("refs/heads/")
        after = payload.get("after")
        if not isinstance(after, str) or after.startswith("0000000"):
            return {"received": True, "queued": False, "reason": "delete_or_empty"}
        rres = (
            sb.table("repositories")
            .select("id, org_id, default_branch")
            .eq("github_repo_id", int(gh_repo_id))
            .limit(1)
            .execute()
        )
        if not rres.data:
            return {"received": True, "queued": False, "reason": "repo_not_registered"}
        repo_row = rres.data[0]
        repo_uuid = str(repo_row["id"])
        org_uuid = str(repo_row["org_id"])
        default_branch = str(repo_row.get("default_branch") or "main")
        snap_args = [repo_uuid, branch, after]
        if not _enqueue("dm.snapshot_repo_branch", snap_args):
            from app.worker.cross_repo_tasks import snapshot_repo_branch

            snapshot_repo_branch(repo_uuid, branch, after)
        if branch == default_branch:
            if not _enqueue("dm.build_org_graph", [org_uuid, None], countdown=10):
                from app.worker.cross_repo_tasks import build_org_graph

                build_org_graph(org_uuid, None)
        else:
            if not _enqueue(
                "dm.compute_branch_drift",
                [repo_uuid, default_branch, branch],
                countdown=15,
            ):
                from app.worker.cross_repo_tasks import compute_branch_drift

                compute_branch_drift(repo_uuid, default_branch, branch)
        return {"received": True, "queued": True, "event": "push"}

    if event == "create":
        ref_type = payload.get("ref_type")
        if ref_type != "branch":
            return {"received": True, "queued": False, "reason": "not_branch_create"}
        repo_js = payload.get("repository") or {}
        gh_repo_id = repo_js.get("id")
        ref = str(payload.get("ref") or "")
        if not gh_repo_id or not ref.startswith("refs/heads/"):
            return {"received": True, "queued": False, "reason": "bad_ref"}
        branch = ref.removeprefix("refs/heads/")
        rres = (
            sb.table("repositories")
            .select("id")
            .eq("github_repo_id", int(gh_repo_id))
            .limit(1)
            .execute()
        )
        if not rres.data:
            return {"received": True, "queued": False, "reason": "repo_not_registered"}
        repo_uuid = str(rres.data[0]["id"])
        sha = (payload.get("sha") or "") or None
        if not _enqueue("dm.snapshot_repo_branch", [repo_uuid, branch, sha]):
            from app.worker.cross_repo_tasks import snapshot_repo_branch

            snapshot_repo_branch(repo_uuid, branch, sha)
        return {"received": True, "queued": True, "event": "create"}

    if event == "delete":
        ref_type = payload.get("ref_type")
        if ref_type != "branch":
            return {"received": True, "queued": False, "reason": "not_branch_delete"}
        repo_js = payload.get("repository") or {}
        gh_repo_id = repo_js.get("id")
        ref = str(payload.get("ref") or "")
        if not gh_repo_id or not ref.startswith("refs/heads/"):
            return {"received": True, "queued": False, "reason": "bad_ref"}
        branch = ref.removeprefix("refs/heads/")
        rres = (
            sb.table("repositories")
            .select("id")
            .eq("github_repo_id", int(gh_repo_id))
            .limit(1)
            .execute()
        )
        if not rres.data:
            return {"received": True, "queued": False, "reason": "repo_not_registered"}
        repo_uuid = str(rres.data[0]["id"])
        if not _enqueue("dm.cleanup_deleted_branch", [repo_uuid, branch]):
            from app.worker.cross_repo_tasks import cleanup_deleted_branch

            cleanup_deleted_branch(repo_uuid, branch)
        return {"received": True, "queued": True, "event": "delete"}

    return {"received": True, "queued": False, "event": event or "unknown"}
