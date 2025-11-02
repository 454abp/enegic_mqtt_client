import os
import json
import requests
import datetime
from pathlib import Path

API_BASE = os.getenv("ENEGIC_API_BASE", "https://api.enegic.com")
USERNAME = os.getenv("ENEGIC_USERNAME", "florian@454abp.de")
PASSWORD = os.getenv("ENEGIC_PASSWORD", "C^KP5z2i971D")
CACHE_FILE = Path(".token_cache.json")


def _save_token(token_info: dict):
    """Speichert TokenInfo lokal in .token_cache.json"""
    CACHE_FILE.write_text(json.dumps(token_info, indent=2))


def _load_token() -> dict | None:
    """Liest TokenInfo aus Cache-Datei, falls vorhanden und gültig"""
    if not CACHE_FILE.exists():
        return None

    try:
        data = json.loads(CACHE_FILE.read_text())
        valid_to = datetime.datetime.fromisoformat(data["ValidTo"].replace("Z", "+00:00"))
        if valid_to > datetime.datetime.now(datetime.timezone.utc):
            return data
        else:
            print("⚠️  Token abgelaufen – hole neuen.")
    except Exception as e:
        print("⚠️  Fehler beim Lesen des Tokens:", e)

    return None


def _request_new_token() -> dict:
    """Fragt neuen Token bei der API an."""
    url = f"{API_BASE}/createtoken"
    payload = {"UserName": USERNAME, "Password": PASSWORD}
    resp = requests.put(url, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    token_info = data.get("TokenInfo")
    if not token_info:
        raise RuntimeError("Keine TokenInfo im API-Response erhalten!")
    _save_token(token_info)
    return token_info


def get_token() -> str:
    """Hauptfunktion: liefert gültigen Token (cached oder neu)"""
    token_info = _load_token()
    if token_info:
        return token_info["Token"]

    token_info = _request_new_token()
    print("✅ Neuer Token abgerufen.")
    return token_info["Token"]


if __name__ == "__main__":
    token = get_token()
    print("Aktueller Token:", token)
