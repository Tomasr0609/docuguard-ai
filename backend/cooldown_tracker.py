"""Global upload cooldown tracker (60s between uploads, shared app-wide).

Persisted in data/cooldown.json. Follows the same pattern as usage_tracker.py:
a flat JSON file, no Redis. This tracks the *cooldown* between uploads, which is
a different concern from the daily request quota (usage_tracker.py).
"""
import json
import time
from pathlib import Path

from backend.config import settings

_COOLDOWN_FILE = Path(__file__).resolve().parent.parent / "data" / "cooldown.json"


def _load_last_upload_at() -> float:
    if _COOLDOWN_FILE.exists():
        try:
            with open(_COOLDOWN_FILE, "r") as f:
                data = json.load(f)
            return float(data.get("last_upload_at", 0.0))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return 0.0


def cooldown_remaining() -> float:
    """Segundos hasta que se pueda subir otro documento. 0 si no hay cooldown."""
    if settings.upload_cooldown_seconds <= 0:
        return 0.0
    last = _load_last_upload_at()
    if not last:
        return 0.0
    return max(0.0, (last + settings.upload_cooldown_seconds) - time.time())


def record_upload() -> None:
    """Registra un upload exitoso, arrancando el cooldown desde ahora."""
    _COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_COOLDOWN_FILE, "w") as f:
        json.dump({"last_upload_at": time.time()}, f)