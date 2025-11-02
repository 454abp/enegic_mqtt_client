import json
import time

import paho.mqtt.client as mqtt

from .config_loader import load_config
from .enegic_client import (
    extract_hub_state_data,
    get_account_overview,
    get_latest_packets,
)

cfg = load_config()
mqtt_cfg = cfg["mqtt"]

BROKER = mqtt_cfg["host"]
PORT = mqtt_cfg["port"]
TOPIC_ROOT = mqtt_cfg["topic_root"]
QOS = mqtt_cfg.get("qos", 0)
RETAIN = mqtt_cfg.get("retain", True)
USERNAME = mqtt_cfg.get("username")
PASSWORD = mqtt_cfg.get("password")
TLS = mqtt_cfg.get("tls", False)

POLL_INTERVAL = cfg["poll_interval"]


def publish(client, topic, payload):
    """Publish a value and keep logging consistent."""
    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload)
    client.publish(topic, payload, qos=QOS, retain=RETAIN)
    print(f"📤 {topic} = {payload}")


def publish_phase_data(client, base_topic, packets):
    """Publish all phase packets (Realtime, Minute, Hour, Day, …)."""
    for period, block in packets.items():
        if not period.startswith("Phase"):
            continue

        data = block.get("data", {})
        suffix = period.replace("Phase", "").lower() or "realtime"
        period_topic = f"{base_topic}/phase/{suffix}"

        currents = data.get("hiavg", []) or []
        voltages = data.get("huavg", []) or []
        energy_in = data.get("hwi")
        energy_out = data.get("hwo")

        for idx, value in enumerate(currents, start=1):
            publish(client, f"{period_topic}/current_L{idx}", round(value, 3))
        for idx, value in enumerate(voltages, start=1):
            publish(client, f"{period_topic}/voltage_L{idx}", round(value, 1))
        if energy_in is not None:
            publish(client, f"{period_topic}/energy_import", round(energy_in, 3))
        if energy_out is not None:
            publish(client, f"{period_topic}/energy_export", round(energy_out, 3))

        print(
            f"📤 {period_topic}: Iavg={currents}, Uavg={voltages}, "
            f"Wi={energy_in}, Wo={energy_out}"
        )


def publish_hub_state(client, base_topic, device_data):
    """Publish hub state metrics."""
    parsed = extract_hub_state_data(device_data)
    hub_topic = f"{base_topic}/hub"

    publish(client, f"{hub_topic}/connected", parsed.get("connected"))
    publish(client, f"{hub_topic}/state", parsed.get("charging_state"))
    publish(client, f"{hub_topic}/rssi", parsed.get("rssi"))

    for idx, value in enumerate(parsed.get("current_mA", []) or [], start=1):
        publish(client, f"{hub_topic}/current_L{idx}", round(value / 1000.0, 3))

    publish(client, f"{hub_topic}/json", parsed)


def main():
    client = mqtt.Client()

    if USERNAME and PASSWORD:
        client.username_pw_set(USERNAME, PASSWORD)

    if TLS:
        client.tls_set()

    client.connect(BROKER, PORT, 60)
    print(f"✅ Verbunden mit MQTT-Broker {BROKER}:{PORT} (TLS={TLS})")

    while True:
        overview = get_account_overview()
        for item in overview.get("Items", []):
            item_id = item.get("ItemId")

            all_data = get_latest_packets(item_id)
            if not isinstance(all_data, list):
                continue

            device_data = next(
                (entry for entry in all_data if entry.get("ItemId") == item_id),
                None,
            )
            if not device_data:
                continue

            packets = device_data.get("LatestPackets", {})
            base_topic = f"{TOPIC_ROOT}/{item_id}"

            if any(key.startswith("Phase") for key in packets):
                publish_phase_data(client, base_topic, packets)
            elif "HubState" in packets:
                publish_hub_state(client, base_topic, device_data)

        print(f"⏳ Warte {POLL_INTERVAL}s …\n")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
