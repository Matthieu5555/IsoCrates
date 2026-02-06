"""
Polling worker for processing documentation regeneration jobs.

Checks the generation_jobs table every POLL_INTERVAL seconds for queued jobs,
claims one at a time, and runs the documentation agent as a subprocess.
Failed jobs are retried once automatically by the JobService.

Additionally, enqueues daily refresh jobs for all tracked repositories
so documentation stays in sync even without webhook pushes.

Usage:
    python worker.py
"""

import os
import sys
import time
import subprocess
import logging
from datetime import datetime, timezone

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app.services.job_service import JobService
from app.services.document_service import DocumentService

# Seconds between polling the job queue
POLL_INTERVAL = 10

# Seconds between daily refresh checks (24 hours)
DAILY_REFRESH_INTERVAL = int(os.getenv("DAILY_REFRESH_INTERVAL", str(24 * 60 * 60)))

# Path to the agent script
AGENT_SCRIPT = os.getenv("AGENT_SCRIPT_PATH", "/workspace/openhands_doc.py")

# How to invoke the agent: "local" runs subprocess directly,
# "docker" execs into the doc-agent container
AGENT_MODE = os.getenv("AGENT_MODE", "docker")

# Maximum seconds a single generation job can run before being killed.
# Large repos with many documents may need up to 20-30 minutes.
# Used by: _run_job() subprocess call. Changing this affects how long
# the worker waits before declaring a job timed out.
JOB_TIMEOUT_SECONDS = 1800  # 30 minutes
AGENT_CONTAINER = os.getenv("AGENT_CONTAINER", "doc-agent")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("worker")


def process_job(job) -> None:
    """
    Run the documentation agent for a single job.

    Spawns `python openhands_doc.py --repo <url>` as a subprocess.
    Updates job status to completed or failed based on the exit code.
    """
    db = SessionLocal()
    try:
        service = JobService(db)
        logger.info(f"Processing job {job.id}: {job.repo_url}")

        if AGENT_MODE == "docker":
            # Execute inside the doc-agent container which has openhands SDK
            cmd = [
                "docker", "exec", AGENT_CONTAINER,
                "python", AGENT_SCRIPT, "--repo", job.repo_url,
            ]
        else:
            # Local mode (for development or when worker has openhands)
            cmd = [sys.executable, AGENT_SCRIPT, "--repo", job.repo_url]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=JOB_TIMEOUT_SECONDS,
        )

        if result.returncode == 0:
            service.complete(job.id)
            logger.info(f"Job {job.id} completed successfully")
        else:
            # Capture enough stderr to be useful for diagnosis.
            # 2000 chars covers most Python tracebacks and structured error summaries.
            # Used by: job_service.fail() → stored in generation_jobs.error_message →
            # returned by GET /api/jobs → displayed in frontend job status tooltip.
            max_error_chars = 2000
            error_msg = result.stderr[-max_error_chars:] if result.stderr else f"Exit code {result.returncode}"
            service.fail(job.id, error_msg)
            logger.warning(f"Job {job.id} failed: {error_msg[:200]}")

    except subprocess.TimeoutExpired:
        service = JobService(db)
        service.fail(job.id, "Job timed out after 30 minutes")
        logger.warning(f"Job {job.id} timed out")
    except Exception as e:
        service = JobService(db)
        service.fail(job.id, str(e))
        logger.error(f"Job {job.id} error: {e}")
    finally:
        db.close()


def enqueue_daily_refreshes() -> int:
    """
    Enqueue a regeneration job for every tracked repository.

    The agent itself handles the "nothing changed" case cheaply —
    it checks the commit SHA against what's stored and exits early
    if the repo hasn't moved. So this is safe to call daily.

    Returns the number of jobs enqueued.
    """
    db = SessionLocal()
    try:
        doc_service = DocumentService(db)
        job_service = JobService(db)

        repo_urls = doc_service.get_tracked_repo_urls()
        if not repo_urls:
            return 0

        count = 0
        for repo_url in repo_urls:
            # Enqueue without a commit_sha so deduplication doesn't
            # block it (we want it to run even if the last webhook
            # job for the same commit completed — the agent will
            # detect "unchanged" and exit early)
            job_service.enqueue(repo_url, commit_sha=None)
            count += 1

        logger.info(f"Daily refresh: enqueued {count} job(s) for {len(repo_urls)} tracked repo(s)")
        return count

    except Exception as e:
        logger.error(f"Failed to enqueue daily refreshes: {e}")
        return 0
    finally:
        db.close()


def main() -> None:
    """Poll for queued jobs and process them sequentially.
    Also triggers daily refresh jobs for all tracked repositories."""
    logger.info(f"Worker started, polling every {POLL_INTERVAL}s")
    logger.info(f"Agent script: {AGENT_SCRIPT}")
    logger.info(f"Daily refresh interval: {DAILY_REFRESH_INTERVAL}s")

    last_daily_refresh = datetime.now(timezone.utc)

    # Run initial daily refresh on startup
    enqueue_daily_refreshes()

    while True:
        db = SessionLocal()
        try:
            # Check if it's time for a daily refresh
            now = datetime.now(timezone.utc)
            elapsed = (now - last_daily_refresh).total_seconds()
            if elapsed >= DAILY_REFRESH_INTERVAL:
                logger.info("Daily refresh triggered")
                enqueue_daily_refreshes()
                last_daily_refresh = now

            # Poll for jobs
            service = JobService(db)
            job = service.claim_next()

            if job:
                db.close()
                process_job(job)
            else:
                db.close()
                time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Worker shutting down")
            db.close()
            break
        except Exception as e:
            logger.error(f"Worker error: {e}")
            db.close()
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
