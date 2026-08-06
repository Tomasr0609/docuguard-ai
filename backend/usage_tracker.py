"""Simple daily request counter for quota protection.

Persisted in data/daily_usage.json. Resets automatically at midnight.
Used primarily to protect the shared Gemini free-tier quota in public deploys.
"""
import json
from datetime import date
from pathlib import Path

from backend.config import settings

_USAGE_FILE = Path(__file__).resolve().parent.parent / "data" / "daily_usage.json"


def _load_usage() -> dict:
    today = str(date.today())
    if _USAGE_FILE.exists():
        with open(_USAGE_FILE, "r") as f:
            data = json.load(f)
        if data.get("date") == today:
            return data
    return {"date": today, "count": 0}


def _save_usage(usage: dict) -> None:
    _USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_USAGE_FILE, "w") as f:
        json.dump(usage, f)


def is_limit_exceeded() -> bool:
    """Return True if today's request count has reached the configured limit.

    Always returns False when daily_request_limit is 0 (unlimited).
    """
    if settings.daily_request_limit <= 0:
        return False
    usage = _load_usage()
    return usage["count"] >= settings.daily_request_limit


def increment_daily_count() -> int:
    """Increment today's request counter and return the new count."""
    usage = _load_usage()
    usage["count"] += 1
    _save_usage(usage)
    return usage["count"]
