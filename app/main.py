import logging
import time
from datetime import date

import redis
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.adapter import AssignmentAdapter
from app.canvas_client import CanvasAuthError, CanvasAPIError, CanvasClient
from app.config import settings
from app.idempotency import IdempotencyService
from app.ls_adapter import LearningSuiteAdapter
from app.sheets_client import SheetsAPIError, SheetsAuthError, SheetsClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="SheetHappens", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://learningsuite.byu.edu"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


class SyncResult(BaseModel):
    status: str
    total_fetched: int
    skipped_duplicates: int
    newly_inserted: int
    failures: int


@app.get("/format")
def format_sheet() -> dict:
    """Reapply all sheet formatting (headers, checkboxes, conditional rules)."""
    try:
        sheets = SheetsClient()
        sheets.reapply_formatting()
        return {"status": "ok", "message": "Formatting reapplied successfully."}
    except (SheetsAuthError, SheetsAPIError) as exc:
        logger.error("Failed to reapply formatting: %s", exc)
        return {"status": "error", "message": str(exc)}


@app.get("/health")
def health() -> dict:
    logger.info("Health check requested")
    return {"status": "ok", "service": "sheethappens"}


def _days_until_end_of_week() -> int:
    """Return the number of days from today until Sunday (end of current week), minimum 1."""
    today = date.today()
    days_left = 6 - today.weekday()  # Monday=0, Sunday=6
    return max(days_left, 1)


@app.get("/sync", response_model=SyncResult)
def sync(
    days: int = Query(default=None, ge=1, le=365, description="How many days ahead to fetch assignments (default: rest of current week)"),
) -> SyncResult:
    if days is None:
        days = _days_until_end_of_week()
    started_at = time.monotonic()
    logger.info("Sync started (window: %d days).", days)

    # --- bootstrap clients ---
    try:
        canvas = CanvasClient()
        adapter = AssignmentAdapter()
        sheets = SheetsClient()
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        idempotency = IdempotencyService(redis_client)
    except Exception as exc:
        logger.error("ALERT: Failed to initialise clients: %s", exc)
        return SyncResult(
            status="error",
            total_fetched=0,
            skipped_duplicates=0,
            newly_inserted=0,
            failures=1,
        )

    # --- fetch & adapt ---
    try:
        raw = canvas.fetch_upcoming_assignments(days=days)
    except CanvasAuthError as exc:
        logger.error("ALERT: Canvas auth failure — token may need rotating: %s", exc)
        return SyncResult(
            status="error",
            total_fetched=0,
            skipped_duplicates=0,
            newly_inserted=0,
            failures=1,
        )
    except CanvasAPIError as exc:
        logger.error("ALERT: Canvas API unreachable — repeated failures may indicate upstream outage: %s", exc)
        return SyncResult(
            status="error",
            total_fetched=0,
            skipped_duplicates=0,
            newly_inserted=0,
            failures=1,
        )

    assignments = adapter.adapt_many(raw)
    total_fetched = len(assignments)
    logger.info("Fetched and adapted %d assignments.", total_fetched)

    # --- deduplicate, write, mark ---
    skipped = 0
    inserted = 0
    failures = 0

    for assignment in assignments:
        try:
            if idempotency.seen(assignment.assignment_id):
                skipped += 1
                continue

            sheets.append_rows([assignment])
            idempotency.mark_seen(assignment.assignment_id)
            inserted += 1

        except (SheetsAPIError, SheetsAuthError) as exc:
            logger.error("Failed to write assignment %s: %s", assignment.assignment_id, exc)
            failures += 1
        except Exception as exc:
            logger.error("Unexpected error for assignment %s: %s", assignment.assignment_id, exc)
            failures += 1

    elapsed = time.monotonic() - started_at

    # --- alerting ---
    if failures > 0 and inserted == 0 and total_fetched > 0:
        logger.error(
            "ALERT: Sync completed with zero inserts and %d failure(s) — investigate Sheets or Redis connectivity.",
            failures,
        )
    elif failures > 0:
        logger.warning(
            "Sync completed with %d failure(s) — some assignments may not have been written.",
            failures,
        )

    logger.info(
        "Sync complete in %.2fs — fetched=%d skipped=%d inserted=%d failures=%d",
        elapsed, total_fetched, skipped, inserted, failures,
    )

    return SyncResult(
        status="ok",
        total_fetched=total_fetched,
        skipped_duplicates=skipped,
        newly_inserted=inserted,
        failures=failures,
    )


class LearningSuiteSyncRequest(BaseModel):
    courses: list[dict]
    page_url: str = ""


class LearningSuiteSyncResult(BaseModel):
    status: str
    synced: int
    skipped: int
    failures: int


@app.post("/sync/learning-suite", response_model=LearningSuiteSyncResult)
def sync_learning_suite(payload: LearningSuiteSyncRequest) -> LearningSuiteSyncResult:
    logger.info("Learning Suite sync started (%d course(s)).", len(payload.courses))

    try:
        sheets = SheetsClient()
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        idempotency = IdempotencyService(redis_client)
    except Exception as exc:
        logger.error("Failed to initialise clients for LS sync: %s", exc)
        return LearningSuiteSyncResult(status="error", synced=0, skipped=0, failures=1)

    assignments = LearningSuiteAdapter().adapt_many(payload.courses, page_url=payload.page_url)
    logger.info("Adapted %d LS assignments.", len(assignments))

    synced = 0
    skipped = 0
    failures = 0

    for assignment in assignments:
        try:
            if idempotency.seen(assignment.assignment_id):
                skipped += 1
                continue
            sheets.append_rows([assignment])
            idempotency.mark_seen(assignment.assignment_id)
            synced += 1
        except (SheetsAPIError, SheetsAuthError) as exc:
            logger.error("Failed to write LS assignment %s: %s", assignment.assignment_id, exc)
            failures += 1
        except Exception as exc:
            logger.error("Unexpected error for LS assignment %s: %s", assignment.assignment_id, exc)
            failures += 1

    logger.info("LS sync complete — synced=%d skipped=%d failures=%d", synced, skipped, failures)
    return LearningSuiteSyncResult(status="ok", synced=synced, skipped=skipped, failures=failures)
