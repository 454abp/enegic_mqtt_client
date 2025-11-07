import requests
from .token_manager import get_token


API_BASE = "https://api.enegic.com"


def get_account_overview():
    token = get_token()
    url = f"{API_BASE}/getaccountoverview"
    headers = {"X-Authorization": token}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_latest_packets(item_id: int):
    token = get_token()
    url = f"{API_BASE}/getlatestpackets"
    headers = {"X-Authorization": token}
    payload = {"ItemId": item_id}
    resp = requests.put(url, headers=headers, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def extract_realtime_phase_data(device_data: dict):
    """Extract average voltage and current values from 'PhaseRealTime'."""
    packets = device_data.get("LatestPackets", {})
    phase_rt = packets.get("PhaseRealTime", {})
    data = phase_rt.get("data", {})

    hiavg = data.get("hiavg", [])
    huavg = data.get("huavg", [])

    return {
        "current_avg": hiavg,
        "voltage_avg": huavg
    }

def extract_hub_state_data(device_data: dict):
    """Extract hub/charger state metrics from the 'HubState' packet."""
    packets = device_data.get("LatestPackets", {})
    hub = packets.get("HubState", {})
    data = hub.get("data", {})

    return {
        "charger_id": data.get("cid"),
        "connected": data.get("conn"),
        "charging_state": data.get("evs"),
        "current_mA": data.get("currcurr", []),
        "firmware": hub.get("fw"),
        "rssi": hub.get("rssi")
    }


def main():
    print("📡 Fetching device overview from Enegic …")
    overview = get_account_overview()
    items = overview.get("Items", [])
    print(f"✅ Found {len(items)} device(s)")

    for item in items:
        item_id = item.get("ItemId")
        name = item.get("Name")
        print(f"\n➡️  Live data for {name} (ItemId={item_id})")

        # GET returns a list -> take the first entry
        all_data = get_latest_packets(item_id)
        if not isinstance(all_data, list) or not all_data:
            print("⚠️  No data returned")
            continue

        # Filter the correct device from the list
        device_data = next((d for d in all_data if d.get("ItemId") == item_id), None)
        if not device_data:
            print(f"⚠️  No record found for ItemId={item_id}")
            continue

        parsed = {}
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
