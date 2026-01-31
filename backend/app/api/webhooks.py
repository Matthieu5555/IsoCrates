"""GitHub webhook endpoint for automatic documentation regeneration."""

import hmac
import hashlib
import logging
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..core.config import settings
from ..schemas.webhook import WebhookResponse
from ..services.job_service import JobService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _verify_github_signature(payload: bytes, signature_header: str, secret: str) -> bool:
    """
    Verify GitHub webhook HMAC-SHA256 signature.

    Args:
        payload: Raw request body bytes
        signature_header: Value of X-Hub-Signature-256 header
        secret: Webhook secret configured in GitHub

    Returns:
        True if signature is valid
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected_sig = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()

    received_sig = signature_header[7:]  # Strip "sha256=" prefix
    return hmac.compare_digest(expected_sig, received_sig)


@router.post("/github", response_model=WebhookResponse)
async def github_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Receive GitHub push webhooks and enqueue documentation regeneration.

    Validates the webhook signature using GITHUB_WEBHOOK_SECRET,
    extracts the repository URL and head commit SHA, and creates
    a generation job. Duplicate pushes for the same commit are
    deduplicated by the job service.
    """
    # Read raw body for signature verification
    body = await request.body()

    # Verify signature if secret is configured
    webhook_secret = settings.github_webhook_secret
    if webhook_secret:
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not _verify_github_signature(body, signature, webhook_secret):
            logger.warning("Webhook signature verification failed")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    else:
        logger.warning("GITHUB_WEBHOOK_SECRET not configured — skipping signature verification")

    # Parse payload
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Only process push events
    event_type = request.headers.get("X-GitHub-Event", "")
    if event_type != "push":
        return WebhookResponse(
            status="ignored",
            message=f"Event type '{event_type}' ignored, only 'push' is processed"
        )

    # Extract repository URL and commit SHA
    repo_data = payload.get("repository", {})
    repo_url = repo_data.get("clone_url") or repo_data.get("html_url")
    if not repo_url:
        raise HTTPException(status_code=400, detail="No repository URL in payload")

    commit_sha = payload.get("head_commit", {}).get("id") or payload.get("after")

    # Enqueue regeneration job
    service = JobService(db)
    job = service.enqueue(repo_url=repo_url, commit_sha=commit_sha)

    return WebhookResponse(
        status="queued",
        job_id=job.id,
        message=f"Regeneration job enqueued for {repo_url}"
    )
