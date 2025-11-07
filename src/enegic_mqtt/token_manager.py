from pathlib import Path
import json, datetime, requests
from .config_loader import load_config

cfg = load_config()
API_BASE = cfg["enegic"]["base_url"]
USERNAME = cfg["enegic"]["username"]
PASSWORD = cfg["enegic"]["password"]
CACHE_FILE = Path(".token_cache.json")



def _save_token(token_info: dict):
    """Persist token info locally in .token_cache.json."""
    CACHE_FILE.write_text(json.dumps(token_info, indent=2))


def _load_token() -> dict | None:
    """Load token info from the cache file if it exists and is still valid."""
    if not CACHE_FILE.exists():
        return None

    try:
        data = json.loads(CACHE_FILE.read_text())
        valid_to = datetime.datetime.fromisoformat(data["ValidTo"].replace("Z", "+00:00"))
        if valid_to > datetime.datetime.now(datetime.timezone.utc):
            return data
        else:
            print("⚠️  Token expired – requesting a new one.")
    except Exception as e:
        print("⚠️  Failed to read cached token:", e)

    return None


def _request_new_token() -> dict:
    """Request a fresh token from the API."""
    url = f"{API_BASE}/createtoken"
    payload = {"UserName": USERNAME, "Password": PASSWORD}
    resp = requests.put(url, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    token_info = data.get("TokenInfo")
    if not token_info:
        raise RuntimeError("No TokenInfo found in API response!")
    _save_token(token_info)
    return token_info


def get_token() -> str:
    """Return a valid token, preferring the cached value when possible."""
    token_info = _load_token()
    if token_info:
        return token_info["Token"]

    token_info = _request_new_token()
    print("✅ Retrieved new token.")
    return token_info["Token"]


if __name__ == "__main__":
    token = get_token()
    print("Current token:", token)
