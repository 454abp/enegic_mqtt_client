# ------------------------------------------------------------
# Original imports and helpers restored
# ------------------------------------------------------------
import argparse
import datetime
import json
import logging
from time import sleep
import requests

from .config_loader import load_config
from .enegic_client import get_account_overview
from .token_manager import get_token
from .site_cache import cache_site_id, load_cached_site_id

cfg = load_config()
enegic_cfg = cfg["enegic"]

API_BASE = enegic_cfg.get("base_url", "https://api.enegic.com").rstrip("/")
HISTORY_TIMEOUT = enegic_cfg.get("history_timeout", 10)
CONFIGURED_SITE_ID = enegic_cfg.get("site_id")
STATIC_HISTORY_TOKEN = enegic_cfg.get("history_token")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ------------------------------------------------------------
# Helpers from original file
# ------------------------------------------------------------
def parse_date(s):
    try:
        if len(s) == 10:
            return datetime.datetime.fromisoformat(s).replace(tzinfo=datetime.timezone.utc)
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        raise argparse.ArgumentTypeError(f"Invalid date/time: {s}")


def fetch_samples(item_id, token, start, end, resolution="Hour", group_by="Day", timeout=10):
    url = f"{API_BASE}/getphasedata"
    headers = {"X-Authorization": token, "Content-Type": "application/json"}
    payload = {
        "ItemID": str(item_id),
        "StartTime": start.isoformat(),
        "EndTime": end.isoformat(),
        "Resolution": resolution.capitalize(),
        "GroupBy": group_by.capitalize(),
        "TimeZone": "Europe/Stockholm",
    }
    resp = requests.put(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def resolve_site_id(cli_site_id, history_token):
    if cli_site_id:
        cache_site_id(cli_site_id, "cli")
        return cli_site_id
    if CONFIGURED_SITE_ID:
        cache_site_id(CONFIGURED_SITE_ID, "config")
        return CONFIGURED_SITE_ID

    cached = load_cached_site_id()
    if cached:
        site_id, _ = cached
        return site_id

    overview = get_account_overview()
    for item in overview.get("Items", []):
        site_id = (
            item.get("SiteId") or item.get("SiteID") or item.get("ItemId") or item.get("ItemID")
        )
        if site_id:
            cache_site_id(site_id, "auto")
            return site_id

    sid = discover_site_id_via_history_api(history_token)
    if sid:
        return sid

    raise RuntimeError("No site_id found. Provide one via --site-id or config.enegic.site_id.")


def resolve_history_token():
    # Prefer explicit token from config
    if STATIC_HISTORY_TOKEN:
        return STATIC_HISTORY_TOKEN
    # Always fetch a fresh token (avoid stale token_cache)
    return get_token()
    if STATIC_HISTORY_TOKEN:
        return STATIC_HISTORY_TOKEN
    return get_token()


def discover_site_id_via_history_api(token):
    url = f"{API_BASE}/v1/sites"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=HISTORY_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return None

    rows = []
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for key in ("sites", "Sites", "items", "Items"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break

    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("siteId", "SiteId", "site_id", "id", "ID"):
            site_id = row.get(key)
            if site_id:
                cache_site_id(site_id, "history_api")
                return site_id
    return None


def print_response(data):
    if not isinstance(data, list):
        print(json.dumps(data, indent=2))
        return
    for day in data:
        date = day.get("dt")
        for entry in day.get("data", []):
            ts = entry.get("ts")
            vals = entry.get("data", {})
            hiavg = vals.get("hiavg")
            huavg = vals.get("huavg")
            hwp1 = vals.get("hwp1")
            print(f"{ts}  Iavg={hiavg}  Uavg={huavg}  P1={hwp1}")

# ------------------------------------------------------------
# MQTT additions remain below
# ------------------------------------------------------------, Influx line protocol, and the history reader logic here.
# Added MQTT output support (generic for GitHub usage).

import paho.mqtt.client as mqtt

class MQTTPublisher:
    def __init__(self, host, port=1883, base_topic="enegic/history"):
        self.host = host
        self.port = port
        self.base_topic = base_topic.rstrip("/")
        self.client = mqtt.Client()
        self.client.connect(self.host, self.port, keepalive=60)

    def publish_point(self, site_id, timestamp, payload_dict):
        """
        Publishes a JSON payload like:
        {
            "value": 8123,
            "timestamp": 1731525900,
            "L1": 2.3,
            "L2": 1.8,
            "L3": 3.1
        }
        Topic example:
        enegic/history/<site_id>/minute/power
        """
        topic = f"{self.base_topic}/{site_id}/minute/power"
        self.client.publish(topic, json.dumps(payload_dict), qos=0, retain=False)

import json
# In main() we will later add:
#   --output mqtt
#   --mqtt-host
#   --mqtt-port
# and wire it to MQTTPublisher

# The next updates will modify functions and add modes for influx/mqtt output.

# ------------------------------------------------------------
# CLI extensions for MQTT output
# ------------------------------------------------------------
def extend_argparser_for_mqtt(parser):
    parser.add_argument("--output", choices=["console", "mqtt"], default="console",
                        help="Select output method: console (default) or mqtt")
    parser.add_argument("--mqtt-host", default="localhost",
                        help="MQTT broker hostname or IP")
    parser.add_argument("--mqtt-port", type=int, default=1883,
                        help="MQTT broker port")
    parser.add_argument("--mqtt-topic-base", default="enegic/history",
                        help="Base MQTT topic for publishing historical data")
    return parser

# ------------------------------------------------------------
# Output dispatcher for sending historic samples to MQTT
# ------------------------------------------------------------
def handle_output_mqtt(publisher: MQTTPublisher, site_id: int, sample: dict):
    """
    sample is expected to be a dict from the Enegic API like:
    {
        "ts": 1731525900,
        "data": {
            "hiavg": ...,   # current / I
            "huavg": ...,   # voltage / U
            "hwp1": ...,    # watt / power
        }
    }
    """
    ts = sample.get("ts")
    vals = sample.get("data", {})

    payload = {
        "timestamp": ts,
    }

    # Map Enegic fields into generic MQTT payload fields
    if "hwp1" in vals:
        payload["power"] = vals["hwp1"]
    if "hiavg" in vals:
        payload["current_avg"] = vals["hiavg"]
    if "huavg" in vals:
        payload["voltage_avg"] = vals["huavg"]

    publisher.publish_point(site_id, ts, payload)

# ------------------------------------------------------------
# Integrate MQTT logic into main()
# ------------------------------------------------------------
from .config_loader import load_config  # ensure imports exist
from .enegic_client import get_account_overview
from .token_manager import get_token
from .site_cache import cache_site_id, load_cached_site_id

def main():
    import argparse
    import datetime
    import logging
    from time import sleep

    parser = argparse.ArgumentParser(description="Fetch historical Enegic data and output via console or MQTT")
    parser.add_argument("--from", dest="from_", type=parse_date, required=True)
    parser.add_argument("--to", dest="to_", type=parse_date, default=datetime.datetime.now(datetime.timezone.utc))
    parser.add_argument("--resolution", choices=["minute", "hour", "day"], default="minute")
    parser.add_argument("--chunk-hours", type=int, default=24)
    parser.add_argument("--json", action="store_true", help="print raw JSON output (console mode only)")
    parser.add_argument("--site-id", type=int, help="override site id; otherwise auto-detect")
    parser.add_argument("--sleep-seconds", type=int, default=1, help="delay between successful chunk requests")
    parser.add_argument("--retry-seconds", type=int, default=5, help="delay after a failed request")

    # extend parser (MQTT flags)
    extend_argparser_for_mqtt(parser)
    args = parser.parse_args()

    token = resolve_history_token()
    site_id = resolve_site_id(args.site_id, token)

    # prepare MQTT if selected
    mqtt_publisher = None
    if args.output == "mqtt":
        mqtt_publisher = MQTTPublisher(
            host=args.mqtt_host,
            port=args.mqtt_port,
            base_topic=args.mqtt_topic_base,
        )

    current = args.from_
    while current < args.to_:
        chunk_end = min(current + datetime.timedelta(hours=args.chunk_hours), args.to_)
        logging.info(f"Fetching {current} → {chunk_end}")
        try:
            data = fetch_samples(
                site_id,
                token,
                current,
                chunk_end,
                args.resolution,
                "Day",  # can adjust if needed
                HISTORY_TIMEOUT,
            )

            # Normalize history API responses (dict with 'samples' or raw list)
            if isinstance(data, list):
                samples = data
            else:
                samples = data.get("samples", [])

            if args.output == "console":
                if args.json:
                    print(json.dumps(data, indent=2))
                else:
                    for s in samples:
                        print_response([s])

            elif args.output == "mqtt":
                for s in samples:
                    handle_output_mqtt(mqtt_publisher, site_id, s)

            sleep(args.sleep_seconds)

        except Exception as e:
            # Auto-refresh token on 401 responses
            if "401" in str(e):
                logging.warning("401 detected — refreshing token and retrying chunk")
                # fetch fresh token and persist
                token = get_token(force_refresh=True)
                # continue with next retry loop
                continue
                logging.warning("401 detected — refreshing token and retrying chunk")
                token = get_token()
                continue

            logging.error(f"Error fetching chunk {current} → {chunk_end}: {e}")
            sleep(args.retry_seconds)

        current = chunk_end

    logging.info("Finished fetching historical data.")

# ------------------------------------------------------------
# Entry point
# ------------------------------------------------------------
if __name__ == "__main__":
    main()

