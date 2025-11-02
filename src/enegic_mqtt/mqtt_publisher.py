import json, time, paho.mqtt.client as mqtt
from .config_loader import load_config
from .enegic_client import (
    get_account_overview, get_latest_packets,
    extract_realtime_phase_data, extract_hub_state_data
)

cfg = load_config()
BROKER = cfg["mqtt"]["host"]
PORT = cfg["mqtt"]["port"]
TOPIC_ROOT = cfg["mqtt"]["topic_root"]
POLL_INTERVAL = cfg["poll_interval"]
QOS = cfg["mqtt"].get("qos", 0)
RETAIN = cfg["mqtt"].get("retain", True)

mqtt_cfg = cfg["mqtt"]

# 🔐: Auth und TLS
USERNAME = mqtt_cfg.get("username")
PASSWORD = mqtt_cfg.get("password")
TLS = mqtt_cfg.get("tls", False)


def publish(client, topic, payload):
    """Hilfsfunktion für sauberes Publish-Logging."""
    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload)
    client.publish(topic, payload, qos=QOS, retain=RETAIN)
    print(f"📤 {topic} = {payload}")

def publish_phase_data(client, base_topic, packets):
    """Publiziert alle vorhandenen Phase-Blöcke (Realtime, Minute, Hour, Day)."""
    for period, block in packets.items():
        if not period.startswith("Phase"):
            continue  # ignoriere HubState etc.
        data = block.get("data", {})
        period_topic = f"{base_topic}/phase/{period.replace('Phase', '').lower() or 'realtime'}"

        ia = data.get("hiavg", [])
        ua = data.get("huavg", [])
        wi = data.get("hwi")
        wo = data.get("hwo")

        for idx, val in enumerate(ia, start=1):
            client.publish(f"{period_topic}/current_L{idx}", round(val, 3))
        for idx, val in enumerate(ua, start=1):
            client.publish(f"{period_topic}/voltage_L{idx}", round(val, 1))
        if wi is not None:
            client.publish(f"{period_topic}/energy_import", round(wi, 3))
        if wo is not None:
            client.publish(f"{period_topic}/energy_export", round(wo, 3))

        print(f"📤 {period_topic}: Iavg={ia}, Uavg={ua}, Wi={wi}, Wo={wo}")


def main():
    client = mqtt.Client()
        # Auth aktivieren, falls gesetzt
    if USERNAME and PASSWORD:
        client.username_pw_set(USERNAME, PASSWORD)

    if TLS:
        client.tls_set()

    client.connect(BROKER, PORT, 60)
    print(f"✅ Verbunden mit MQTT-Broker {BROKER}:{PORT} (TLS={TLS})")
    client.connect(BROKER, PORT, 60)
    print("✅ Verbunden mit MQTT-Broker")

    while True:
        overview = get_account_overview()
        for item in overview.get("Items", []):
            item_id = item.get("ItemId")
            name = item.get("Name")
            all_data = get_latest_packets(item_id)
            if not isinstance(all_data, list):
                continue
            device_data = next((d for d in all_data if d.get("ItemId") == item_id), None)
            if not device_data:
                continue
            packets = device_data.get("LatestPackets", {})
            base_topic = f"{TOPIC_ROOT}/{item_id}"

            # --- Phase-Daten (alle Intervalle) ---
            if any(k.startswith("Phase") for k in packets.keys()):
                publish_phase_data(client, base_topic, packets)

            # --- Hub-Daten ---
            elif "HubState" in packets:
                parsed = extract_hub_state_data(device_data)
                hub_topic = f"{base_topic}/hub"
                publish(client, f"{hub_topic}/connected", parsed.get("connected"))
                publish(client, f"{hub_topic}/state", parsed.get("charging_state"))
                publish(client, f"{hub_topic}/rssi", parsed.get("rssi"))
                currents = parsed.get("current_mA", [])
                for idx, val in enumerate(currents, start=1):
                    publish(client, f"{hub_topic}/current_L{idx}", round(val / 1000.0, 3))
                publish(client, f"{hub_topic}/json", parsed)


            elif "HubState" in packets:
                parsed = extract_hub_state_data(device_data)
                hub_topic = f"{base_topic}/hub"
                publish(client, f"{hub_topic}/connected", parsed.get("connected"))
                publish(client, f"{hub_topic}/state", parsed.get("charging_state"))
                publish(client, f"{hub_topic}/rssi", parsed.get("rssi"))
                currents = parsed.get("current_mA", [])
                for idx, val in enumerate(currents, start=1):
                    publish(client, f"{hub_topic}/current_L{idx}", round(val / 1000.0, 3))
                publish(client, f"{hub_topic}/json", parsed)


        print(f"⏳ Warte {POLL_INTERVAL}s …\n")
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
