"""
Polling worker for processing documentation regeneration jobs.

Checks the generation_jobs table every POLL_INTERVAL seconds for queued jobs,
claims one at a time, and runs the documentation agent as a subprocess.
Failed jobs are retried once automatically by the JobService.

Usage:
    python worker.py
"""

import os
import sys
import time
import subprocess
import logging

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app.services.job_service import JobService

# Seconds between polling the job queue
POLL_INTERVAL = 10

# Path to the agent script (inside Docker, the agent workspace is mounted)
AGENT_SCRIPT = os.getenv("AGENT_SCRIPT_PATH", "/workspace/openhands_doc.py")

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

        result = subprocess.run(
            [sys.executable, AGENT_SCRIPT, "--repo", job.repo_url],
            capture_output=True,
            text=True,
            timeout=1800,  # 30 minute timeout per job
        )

        if result.returncode == 0:
            service.complete(job.id)
            logger.info(f"Job {job.id} completed successfully")
        else:
            error_msg = result.stderr[-500:] if result.stderr else f"Exit code {result.returncode}"
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


def main() -> None:
    """Poll for queued jobs and process them sequentially."""
    logger.info(f"Worker started, polling every {POLL_INTERVAL}s")
    logger.info(f"Agent script: {AGENT_SCRIPT}")

    while True:
        db = SessionLocal()
        try:
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
