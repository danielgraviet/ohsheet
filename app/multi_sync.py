"""Per-user sync logic for multi-tenant Canvas and Learning Suite sync."""
from __future__ import annotations

import logging
from datetime import datetime

from app import crypto, user_repo
from app.adapter import AssignmentAdapter
from app.canvas_client import CanvasAPIError, CanvasAuthError, CanvasClient
from app.ls_adapter import LearningSuiteAdapter
from app.models import Assignment
from app.sheets_client import SheetsAPIError, SheetsAuthError, UserSheetsClient

logger = logging.getLogger(__name__)


class SyncError(Exception):
    pass


async def _load_user_clients(
    sync_token: str,
) -> tuple[dict, dict, UserSheetsClient]:
    """Resolve sync_token → user row + google_account row + UserSheetsClient."""
    user = await user_repo.get_user_by_sync_token(sync_token)
    if not user:
        raise SyncError("invalid_token")

    ga = await user_repo.get_google_account(str(user["id"]))
    if not ga:
        raise SyncError("google_not_connected")
    if not ga.get("spreadsheet_id"):
        raise SyncError("no_spreadsheet")

    access_token = crypto.decrypt(ga["access_token_encrypted"]) if ga.get("access_token_encrypted") else ""
    refresh_token = crypto.decrypt(ga["refresh_token_encrypted"])

    sheets = UserSheetsClient(
        spreadsheet_id=ga["spreadsheet_id"],
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=ga.get("token_expires_at"),
        canvas_domain=user.get("canvas_domain") or "",
    )

    # Persist refreshed tokens if they changed
    if sheets.refreshed_creds and sheets.refreshed_creds.token != access_token:
        new_access_enc = crypto.encrypt(sheets.refreshed_creds.token)
        await user_repo.update_google_tokens(
            str(user["id"]), new_access_enc, sheets.refreshed_creds.expiry
        )

    return user, ga, sheets


async def sync_canvas(sync_token: str, days: int = 30) -> dict:
    """Fetch Canvas assignments and write new ones to the user's Sheet."""
    try:
        user, ga, sheets = await _load_user_clients(sync_token)
    except SyncError as exc:
        return {"status": "error", "error": str(exc), "total_fetched": 0,
                "skipped_duplicates": 0, "newly_inserted": 0, "failures": 0}

    user_id = str(user["id"])

    if not user.get("canvas_token_encrypted"):
        return {"status": "error", "error": "canvas_not_connected", "total_fetched": 0,
                "skipped_duplicates": 0, "newly_inserted": 0, "failures": 0}

    canvas_token = crypto.decrypt(user["canvas_token_encrypted"])
    canvas_domain = user.get("canvas_domain") or ""

    try:
        canvas = CanvasClient(token=canvas_token, domain=canvas_domain)
        raw = canvas.fetch_upcoming_assignments(days=days)
    except CanvasAuthError as exc:
        logger.error("Canvas auth failure for user %s: %s", user_id, exc)
        return {"status": "error", "error": "canvas_auth", "total_fetched": 0,
                "skipped_duplicates": 0, "newly_inserted": 0, "failures": 0}
    except CanvasAPIError as exc:
        logger.error("Canvas API error for user %s: %s", user_id, exc)
        return {"status": "error", "error": "canvas_api", "total_fetched": 0,
                "skipped_duplicates": 0, "newly_inserted": 0, "failures": 0}

    assignments = AssignmentAdapter().adapt_many(raw)
    return await _write_assignments(user_id, assignments, sheets, prefix="canvas")


async def sync_learning_suite(sync_token: str, courses: list[dict], page_url: str = "") -> dict:
    """Adapt Learning Suite data and write new rows to the user's Sheet."""
    try:
        user, ga, sheets = await _load_user_clients(sync_token)
    except SyncError as exc:
        return {"status": "error", "error": str(exc), "synced": 0, "skipped": 0, "failures": 0}

    user_id = str(user["id"])
    assignments = LearningSuiteAdapter().adapt_many(courses, page_url=page_url)
    result = await _write_assignments(user_id, assignments, sheets, prefix="ls")
    return {
        "status": result["status"],
        "synced": result["newly_inserted"],
        "skipped": result["skipped_duplicates"],
        "failures": result["failures"],
    }


async def _write_assignments(
    user_id: str,
    assignments: list[Assignment],
    sheets: UserSheetsClient,
    prefix: str,
) -> dict:
    total = len(assignments)
    item_keys = [f"{prefix}:{a.assignment_id}" for a in assignments]

    already_seen = await user_repo.bulk_seen(user_id, item_keys)
    new_assignments = [a for a, k in zip(assignments, item_keys) if k not in already_seen]
    new_keys = [k for k in item_keys if k not in already_seen]

    skipped = total - len(new_assignments)
    inserted = 0
    failures = 0

    if new_assignments:
        try:
            sheets.append_rows(new_assignments)
            await user_repo.bulk_mark_seen(user_id, new_keys)
            inserted = len(new_assignments)
        except (SheetsAPIError, SheetsAuthError) as exc:
            logger.error("Sheets write error for user %s: %s", user_id, exc)
            failures = len(new_assignments)
        except Exception as exc:
            logger.error("Unexpected write error for user %s: %s", user_id, exc)
            failures = len(new_assignments)

    logger.info(
        "Sync complete for user %s — fetched=%d skipped=%d inserted=%d failures=%d",
        user_id, total, skipped, inserted, failures,
    )
    return {
        "status": "ok",
        "total_fetched": total,
        "skipped_duplicates": skipped,
        "newly_inserted": inserted,
        "failures": failures,
    }
