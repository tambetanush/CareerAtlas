"""Live jobs for the public landing page.

GET /api/public-jobs/ returns the cached rows. When they are older than a week it
starts a refresh in the background and still answers with what it has, so the
landing page never waits on Adzuna. No cron needed: the first visitor after a week
triggers the refresh. Only real Adzuna listings are ever stored.
"""
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks

from app.dependencies.database import db_client
from app.job_hunter.agent import fetch_jobs

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/public-jobs", tags=["Public jobs"])

ROLES = ["Machine Learning Engineer", "Data Analyst", "Backend Engineer"]
PER_ROLE = 3
REFRESH_EVERY = timedelta(days=7)
RETRY_AFTER = timedelta(hours=1)  # after a failed refresh, don't hit Adzuna on every page view

_lock = threading.Lock()
_last_attempt: datetime | None = None


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def is_due(newest: datetime | None, last_attempt: datetime | None, now: datetime) -> bool:
    if newest and now - newest < REFRESH_EVERY:
        return False
    return not (last_attempt and now - last_attempt < RETRY_AFTER)


MAX_AGE = timedelta(days=30)  # Adzuna still returns years-old postings; the landing page must look current


def rows_from_jobs(role: str, jobs: list[dict], fetched_at: str) -> list[dict]:
    rows = []
    cutoff = _parse_ts(fetched_at) - MAX_AGE
    for j in jobs:
        if not (j.get("title") and j.get("apply_url")):
            continue
        posted = _parse_ts(j.get("created"))
        if posted is None or posted < cutoff:
            continue
        rows.append({
            "role_title": role,
            "title": j["title"],
            "company": j.get("company"),
            "location": j.get("location"),
            "apply_url": j["apply_url"],
            "salary_min": j.get("salary_min"),
            "salary_max": j.get("salary_max"),
            "posted_at": j.get("created"),
            "fetched_at": fetched_at,
        })
        if len(rows) == PER_ROLE:
            break
    return rows


def refresh_public_jobs() -> None:
    global _last_attempt
    if not _lock.acquire(blocking=False):
        return  # a refresh is already running in this process
    try:
        _last_attempt = datetime.now(timezone.utc)
        fetched_at = _last_attempt.isoformat()
        rows: list[dict] = []
        for role in ROLES:
            try:
                rows += rows_from_jobs(role, fetch_jobs(role, "", results=10), fetched_at)
            except Exception:
                logger.warning("public jobs: Adzuna fetch failed for %s", role, exc_info=True)
        if not rows:
            logger.warning("public jobs: nothing fetched; keeping the previous listings")
            return
        # Insert first, then drop older batches, so the page is never empty mid-refresh.
        db_client.table("public_jobs").insert(rows).execute()
        db_client.table("public_jobs").delete().lt("fetched_at", fetched_at).execute()
        logger.info("public jobs: refreshed %d listings", len(rows))
    except Exception:
        logger.exception("public jobs refresh failed")
    finally:
        _lock.release()


@router.get("/")
def list_public_jobs(background: BackgroundTasks):
    try:
        rows = (
            db_client.table("public_jobs")
            .select("role_title,title,company,location,apply_url,salary_min,salary_max,posted_at,fetched_at")
            .order("fetched_at", desc=True)
            .limit(len(ROLES) * PER_ROLE)
            .execute()
            .data
            or []
        )
    except Exception:
        # Landing page must not break (e.g. migration 008 not applied yet).
        logger.exception("public_jobs read failed")
        return {"jobs": [], "fetched_at": None}

    newest = _parse_ts(rows[0]["fetched_at"]) if rows else None
    if is_due(newest, _last_attempt, datetime.now(timezone.utc)):
        background.add_task(refresh_public_jobs)

    jobs = [{k: v for k, v in r.items() if k != "fetched_at"} for r in rows]
    return {"jobs": jobs, "fetched_at": rows[0]["fetched_at"] if rows else None}
