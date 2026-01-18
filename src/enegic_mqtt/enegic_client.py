import requests

from .token_manager import get_token, invalidate_token

API_BASE = "https://api.enegic.com"


def _apply_auth(headers: dict | None, token: str) -> dict:
    """Build headers for Enegic API calls.

    Some Enegic endpoints accept the token via X-Authorization, others via Bearer.
    We set both to maximize compatibility.
    """
    h = dict(headers or {})
    h["X-Authorization"] = token
    h["Authorization"] = f"Bearer {token}"
    h.setdefault("Accept", "*/*")
    h.setdefault("User-Agent", "enegic_mqtt/1.0")
    return h


def _request(
    method: str,
    url: str,
    *,
    timeout: int = 15,
    headers: dict | None = None,
    **kwargs,
):
    """HTTP request wrapper with automatic token refresh on 401."""
    token = get_token()
    h = _apply_auth(headers, token)
    resp = requests.request(method, url, headers=h, timeout=timeout, **kwargs)

    if resp.status_code == 401:
        invalidate_token()
        token = get_token(force_refresh=True)
        h = _apply_auth(headers, token)
        resp = requests.request(method, url, headers=h, timeout=timeout, **kwargs)

    resp.raise_for_status()
    return resp


def get_account_overview() -> dict:
    url = f"{API_BASE}/getaccountoverview"
    return _request("GET", url).json()


def get_latest_packets(item_id: int) -> list:
    url = f"{API_BASE}/getlatestpackets"
    payload = {"ItemId": item_id}
    return _request("PUT", url, json=payload).json()


def extract_realtime_phase_data(device_data: dict) -> dict:
    packets = device_data.get("LatestPackets", {})
    phase_rt = packets.get("PhaseRealTime", {})
    data = phase_rt.get("data", {})

    return {
        "current_avg": data.get("hiavg", []),
        "voltage_avg": data.get("huavg", []),
    }


def extract_hub_state_data(device_data: dict) -> dict:
    packets = device_data.get("LatestPackets", {})
    hub = packets.get("HubState", {})
    data = hub.get("data", {})

    return {
        "charger_id": data.get("cid"),
        "connected": data.get("conn"),
        "charging_state": data.get("evs"),
        "current_mA": data.get("currcurr", []),
        "firmware": hub.get("fw"),
        "rssi": hub.get("rssi"),
    }


def main() -> None:
    print("📡 Fetching device overview from Enegic …")
    overview = get_account_overview()
    items = overview.get("Items", [])
    print(f"✅ Found {len(items)} device(s)")

    for item in items:
        item_id = item.get("ItemId")
        name = item.get("Name")
        print(f"\n➡️  Live data for {name} (ItemId={item_id})")

        all_data = get_latest_packets(item_id)
        if not isinstance(all_data, list) or not all_data:
            print("⚠️  No data returned")
            continue

        device_data = next((d for d in all_data if d.get("ItemId") == item_id), None)
        if not device_data:
            print(f"⚠️  No record found for ItemId={item_id}")
            continue

        packets = device_data.get("LatestPackets", {})

        if "PhaseRealTime" in packets:
            parsed = extract_realtime_phase_data(device_data)
            print(f"Iavg = {parsed['current_avg']}, Uavg = {parsed['voltage_avg']}")

        elif "HubState" in packets:
            parsed = extract_hub_state_data(device_data)
            print(
                f"🔌 Hub {parsed['charger_id']}  |  Connected: {parsed['connected']}  |  State: {parsed['charging_state']}"
            )
            print(f"Currents (mA): {parsed['current_mA']}")


if __name__ == "__main__":
    main()
