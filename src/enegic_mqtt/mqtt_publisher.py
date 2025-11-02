import json
import paho.mqtt.client as mqtt
from .enegic_client import get_account_overview, get_latest_packets, extract_realtime_phase_data, extract_hub_state_data
import time

BROKER = "mqtt.wanninger.454abp.de"      # <- dein MQTT-Broker
PORT = 1883
TOPIC_ROOT = "enegic"
POLL_INTERVAL = 5              # Sekunden

def publish(client, topic, payload):
    """Hilfsfunktion für sauberes Publish-Logging."""
    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload)
    client.publish(topic, payload, qos=0, retain=True)
    print(f"📤 {topic} = {payload}")

def main():
    client = mqtt.Client()
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

            # --- Phase-Daten ---
            if "PhaseRealTime" in packets:
                parsed = extract_realtime_phase_data(device_data)
                ia = parsed.get("current_avg", [])
                ua = parsed.get("voltage_avg", [])
                # Einzelne Werte
                for idx, val in enumerate(ia, start=1):
                    publish(client, f"{base_topic}/phase/current_L{idx}", round(val, 2))
                for idx, val in enumerate(ua, start=1):
                    publish(client, f"{base_topic}/phase/voltage_L{idx}", round(val, 1))
                if ia and ua:
                    total_power = sum(i * u for i, u in zip(ia, ua))
                    publish(client, f"{base_topic}/phase/power_total", round(total_power, 1))
                publish(client, f"{base_topic}/phase/json", parsed)

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

        print(f"⏳ Warte {POLL_INTERVAL}s …\n")
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
