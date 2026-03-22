import logging
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.models import Assignment

logger = logging.getLogger(__name__)

_MT = ZoneInfo("America/Denver")
_UTC = ZoneInfo("UTC")

# Reuse the same normalization patterns as the Canvas adapter.
_COURSE_NAME_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bREL\b", re.IGNORECASE), "REL"),
    (re.compile(r"\bMATH\s*112\b", re.IGNORECASE), "MATH 112"),
    (re.compile(r"\bC\s*S\s*180\b", re.IGNORECASE), "CS 180"),
    (re.compile(r"\bC\s*S\s*270\b", re.IGNORECASE), "CS 270"),
]


def _normalize_course_name(raw_name: str) -> str:
    for pattern, label in _COURSE_NAME_PATTERNS:
        if pattern.search(raw_name):
            return label
    return raw_name


def _parse_due_date(due_date_str: str) -> datetime | None:
    """Parse a Learning Suite date string (local MT, no tz) → UTC-aware datetime."""
    try:
        naive = datetime.strptime(due_date_str, "%Y-%m-%d %H:%M:%S")
        return naive.replace(tzinfo=_MT).astimezone(_UTC)
    except (ValueError, TypeError):
        return None


class LearningSuiteAdapter:
    """Maps raw Learning Suite courseInformation dicts to Assignment models."""

    def adapt_many(self, courses: list[dict[str, Any]], page_url: str = "") -> list[Assignment]:
        """Flatten all courses → assignments, returning only successfully adapted ones."""
        results: list[Assignment] = []
        for course in courses:
            course_name = _normalize_course_name(
                (course.get("title") or "Unknown Course").strip()
            )
            for raw in course.get("assignments") or []:
                assignment = self._adapt_one(raw, course_name, page_url)
                if assignment is not None:
                    results.append(assignment)
        return results

    def _adapt_one(self, raw: dict[str, Any], course_name: str, page_url: str = "") -> Assignment | None:
        try:
            assignment_id = str(raw.get("id") or "").strip()
            if not assignment_id:
                logger.warning("Skipping LS item with no id: %s", raw)
                return None

            due_date_raw = raw.get("dueDate")
            if not due_date_raw:
                return None  # skip undated items silently

            due_at = _parse_due_date(due_date_raw)
            if due_at is None:
                logger.warning("Could not parse dueDate '%s' for LS item %s", due_date_raw, assignment_id)
                return None

            assignment_name = (raw.get("name") or "Untitled Assignment").strip()

            return Assignment(
                assignment_id=f"ls_{assignment_id}",
                course_name=course_name,
                assignment_name=assignment_name,
                due_at=due_at,
                url=page_url,
                source="Learning Suite",
            )

        except Exception as exc:
            logger.warning("Failed to adapt LS item: %s — %s", raw, exc)
            return None
