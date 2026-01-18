# Enhanced token_manager.py with cache invalidation
from pathlib import Path
import json
import datetime
import requests
from .config_loader import load_config

cfg = load_config()
API_BASE = cfg["enegic"]["base_url"]
USERNAME = cfg["enegic"]["username"]
PASSWORD = cfg["enegic"]["password"]

CACHE_FILE = Path(".token_cache.json")


def _save_token(token_info: dict):
    CACHE_FILE.write_text(json.dumps(token_info, indent=2))


def invalidate_token():
    try:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
    except Exception:
        pass


def _load_token() -> dict | None:
    if not CACHE_FILE.exists():
        return None

    try:
        data = json.loads(CACHE_FILE.read_text())
        token = data.get("Token")
        valid_to = datetime.datetime.fromisoformat(
            data["ValidTo"].replace("Z", "+00:00")
        )

        if not token or token == "00000000-0000-0000-0000-000000000000":
            return None

        if valid_to > datetime.datetime.now(datetime.timezone.utc):
            return data
    except Exception:
        pass

    return None


def _request_new_token() -> dict:
    url = f"{API_BASE}/createtoken"
    payload = {"UserName": USERNAME, "Password": PASSWORD}
    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "User-Agent": "enegic_mqtt/1.0",
    }

    resp = requests.put(url, headers=headers, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    token_info = data.get("TokenInfo") or {
        "Token": data.get("Token"),
        "ValidTo": data.get("ValidTo"),
    }

    if not token_info or not token_info.get("Token"):
        raise RuntimeError("No TokenInfo found in API response")

    _save_token(token_info)
    return token_info


def get_token(force_refresh: bool = False) -> str:
    token_info = None

    if not force_refresh:
        token_info = _load_token()

    if not token_info:
        token_info = _request_new_token()

    return token_info["Token"]


def auth_headers(token: str) -> dict:
    return {
        "Accept": "*/*",
        "User-Agent": "enegic_mqtt/1.0",
        "Authorization": f"Bearer {token}",
    }
