"""Helpers for caching the detected Enegic site id locally."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

SITE_CACHE_FILE = Path(".site_cache.json")


def cache_site_id(site_id: int, source: str) -> None:
    """Persist the resolved site id along with its origin and timestamp."""

    payload = {
        "site_id": site_id,
        "source": source,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
    SITE_CACHE_FILE.write_text(json.dumps(payload, indent=2))


def load_cached_site_id() -> Optional[Tuple[int, Optional[str]]]:
    """Return the cached site id if present, otherwise ``None``."""

    if not SITE_CACHE_FILE.exists():
        return None

    try:
        data = json.loads(SITE_CACHE_FILE.read_text())
    except Exception as exc:
        print(f"⚠️  Failed to read cached site id: {exc}")
        return None

    site_id = data.get("site_id")
    if site_id is None:
        return None

    return site_id, data.get("source")
