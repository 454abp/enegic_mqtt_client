import argparse
import datetime as dt
import json
import logging
import time
from typing import Any

import requests
import paho.mqtt.client as mqtt

from .config_loader import load_config
from .enegic_client import get_account_overview
from .site_cache import cache_site_id, load_cached_site_id
from .token_manager import get_token, invalidate_token

log = logging.getLogger(__name__)


def parse_date(s: str) -> dt.datetime:
    try:
        if len(s) == 10:
            return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception as e:
        raise argparse.ArgumentTypeError(f"Invalid date/time: {s}") from e


def _apply_auth(headers: dict | None, token: str) -> dict:
    h = dict(headers or {})
    # Enegic endpoints vary; X-Authorization is commonly required.
    h["X-Authorization"] = token
    h["Authorization"] = f"Bearer {token}"
    h.setdefault("Accept", "*/*")
    h.setdefault("User-Agent", "enegic_history_reader/1.0")
    h.setdefault("Content-Type", "application/json")
    return h


def _request(method: str, url: str, *, timeout: int, headers: dict | None = None, **kwargs) -> requests.Response:
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


def fetch_phase_data(
    api_base: str,
    item_id: int,
    start: dt.datetime,
    end: dt.datetime,
    *,
    resolution: str = "Hour",
    group_by: str = "Day",
    timezone: str = "Europe/Stockholm",
    timeout: int = 15,
) -> Any:
    url = f"{api_base}/getphasedata"
    payload = {
        "ItemID": str(item_id),
        "StartTime": start.isoformat(),
        "EndTime": end.isoformat(),
        "Resolution": resolution.capitalize(),
        "GroupBy": group_by.capitalize(),
        "TimeZone": timezone,
    }
    return _request("PUT", url, timeout=timeout, json=payload).json()


def resolve_site_id(cli_site_id: int | None, configured_site_id: int | None) -> int:
    if cli_site_id:
        cache_site_id(cli_site_id, "cli")
        return cli_site_id

    if configured_site_id:
        cache_site_id(configured_site_id, "config")
        return configured_site_id

    cached = load_cached_site_id()
    if cached:
        sid, _src = cached
        return int(sid)

    overview = get_account_overview()
    for item in overview.get("Items", []):
        sid = item.get("SiteId") or item.get("SiteID") or item.get("ItemId") or item.get("ItemID")
        if sid:
            cache_site_id(int(sid), "auto")
            return int(sid)

    raise RuntimeError("No site_id found. Provide one via --site-id or config.enegic.site_id.")


def iter_samples(payload: Any):
    """
    Normalizes Enegic history responses into an iterator of samples.
    We support:
      - list of day-blocks: [{"dt":..., "data":[{"ts":..., "data":{...}}, ...]}, ...]
      - dict with "data" as day-block list
      - dict with "samples" as flat list
      - flat list of samples
    """
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            payload = payload["data"]
        elif isinstance(payload.get("samples"), list):
            for s in payload["samples"]:
                yield s
            return

    if isinstance(payload, list):
        # day-block style
        if payload and isinstance(payload[0], dict) and "data" in payload[0] and isinstance(payload[0]["data"], list):
            for day in payload:
                for sample in day.get("data", []):
                    yield sample
            return

        # flat list style
        for s in payload:
            yield s
        return

    # unknown structure
    return


class MQTTPublisher:
    def __init__(self, host: str, port: int = 1883, base_topic: str = "enegic/history"):
        self.host = host
        self.port = port
        self.base_topic = base_topic.rstrip("/")
        self.client = mqtt.Client()
        self.client.connect(self.host, self.port, keepalive=60)

    def publish_json(self, topic: str, payload_obj: dict):
        self.client.publish(topic, json.dumps(payload_obj), qos=0, retain=False)

    
    
    def publish_as_history_topics(self, device_id: int, resolution: str, sample: dict):
        ts = sample.get("ts")
        vals = sample.get("data", {}) or {}
        res = resolution.lower()

        def pub(metric: str, value: float | int):
            topic = f"{self.base_topic}/{device_id}/phase/{res}/{metric}"
            self.publish_json(topic, {"ts": ts, "value": value})

        hiavg = vals.get("hiavg")
        if isinstance(hiavg, list) and len(hiavg) >= 3:
            pub("current_L1", hiavg[0]); pub("current_L2", hiavg[1]); pub("current_L3", hiavg[2])

        huavg = vals.get("huavg")
        if isinstance(huavg, list) and len(huavg) >= 3:
            pub("voltage_L1", huavg[0]); pub("voltage_L2", huavg[1]); pub("voltage_L3", huavg[2])

    
    def publish_sample(self, site_id: int, resolution: str, sample: dict):
        ts = sample.get("ts")

        # If ts has no timezone, assume UTC and append Z
        if isinstance(ts, str) and ("Z" not in ts) and ("+" not in ts) and ("-" not in ts[10:]):
        ts = ts + "Z"

        vals = sample.get("data", {}) if isinstance(sample, dict) else {}

        payload = {"ts": ts, "data": vals}
        topic = f"{self.base_topic}/{site_id}/{resolution.lower()}"
        self.publish_json(topic, payload)



def publish_as_live_topics(self, device_id: str, resolution: str, sample: dict):
    ts = sample.get("ts")
    vals = sample.get("data", {}) or {}
    res = resolution.lower()

    def pub(metric: str, value: float | int):
        topic = f"enegic/{device_id}/phase/{res}/{metric}"
        self.publish_json(topic, {"ts": ts, "value": value})

    # Example mapping (adjust to your API keys)
    # If hiavg/huavg are per-phase lists:
    hiavg = vals.get("hiavg")
    if isinstance(hiavg, list) and len(hiavg) >= 3:
        pub("current_L1", hiavg[0]); pub("current_L2", hiavg[1]); pub("current_L3", hiavg[2])

    huavg = vals.get("huavg")
    if isinstance(huavg, list) and len(huavg) >= 3:
        pub("voltage_L1", huavg[0]); pub("voltage_L2", huavg[1]); pub("voltage_L3", huavg[2])

    # If you have totals for import/export you want:
    if isinstance(vals.get("energy_import"), (int,float)):
        pub("energy_import", vals["energy_import"])
    if isinstance(vals.get("energy_export"), (int,float)):
        pub("energy_export", vals["energy_export"])

def main():
    cfg = load_config()
    enegic_cfg = cfg["enegic"]

    api_base = enegic_cfg.get("base_url", "https://api.enegic.com").rstrip("/")
    timeout = int(enegic_cfg.get("history_timeout", 15))
    configured_site_id = enegic_cfg.get("site_id")

    parser = argparse.ArgumentParser(description="Fetch historical Enegic phase data (chunked).")

    # default last 30 days
    now = dt.datetime.now(dt.timezone.utc)
    default_from = now - dt.timedelta(days=30)

    parser.add_argument("--from", dest="from_", type=parse_date, default=default_from)
    parser.add_argument("--to", dest="to_", type=parse_date, default=now)

    parser.add_argument("--site-id", type=int, help="Override site id; otherwise auto-detect")
    parser.add_argument("--resolution", choices=["minute", "hour", "day"], default="hour")
    parser.add_argument("--group-by", choices=["day", "hour", "none"], default="day")
    parser.add_argument("--chunk-hours", type=int, default=24)
    parser.add_argument("--sleep-seconds", type=int, default=1)
    parser.add_argument("--retry-seconds", type=int, default=5)

    parser.add_argument("--output", choices=["console", "json", "mqtt"], default="console")
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--mqtt-topic-base", default="enegic/history")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    site_id = resolve_site_id(args.site_id, configured_site_id)
    log.info("Using site_id=%s", site_id)

    mqtt_pub = None
    if args.output == "mqtt":
        mqtt_pub = MQTTPublisher(args.mqtt_host, args.mqtt_port, args.mqtt_topic_base)
        log.info("MQTT output enabled: %s:%s topic=%s", args.mqtt_host, args.mqtt_port, args.mqtt_topic_base)

    # normalize group_by
    group_by = args.group_by
    if group_by == "none":
        group_by = "Day"  # API seems to like a value; Day is safest
    else:
        group_by = group_by.capitalize()

    start = args.from_
    end = args.to_
    if start >= end:
        raise SystemExit("--from must be < --to")

    current = start
    while current < end:
        chunk_end = min(current + dt.timedelta(hours=args.chunk_hours), end)
        log.info("Fetching %s -> %s", current.isoformat(), chunk_end.isoformat())

        try:
            payload = fetch_phase_data(
                api_base,
                site_id,
                current,
                chunk_end,
                resolution=args.resolution.capitalize(),
                group_by=group_by,
                timezone="Europe/Stockholm",
                timeout=timeout,
            )

            if args.output == "json":
                print(json.dumps(payload, indent=2))

            else:
                for sample in iter_samples(payload) or []:
                    if args.output == "mqtt" and mqtt_pub:
                        mqtt_pub.publish_as_history_topics(site_id, args.resolution, sample)
                    else:
                        ts = sample.get("ts")
                        vals = sample.get("data", {})
                        hiavg = vals.get("hiavg")
                        huavg = vals.get("huavg")
                        p_import = vals.get("hwpi")  # list (per phase)
                        p_export = vals.get("hwpo")
                        print(f"{ts}  Iavg={hiavg}  Uavg={huavg}  P_import={p_import}  P_export={p_export}")
                        p_total = sum(vals.get("hwpi") or [])

            time.sleep(args.sleep_seconds)
            current = chunk_end

        except Exception as e:
            msg = str(e)
            if "401" in msg or "Unauthorized" in msg:
                log.warning("401 detected - clearing token and retrying same chunk")
                invalidate_token()
                # next loop iteration retries same chunk
                time.sleep(1)
                continue

            log.error("Error fetching chunk %s -> %s: %s", current, chunk_end, e)
            time.sleep(args.retry_seconds)

    log.info("Finished.")


if __name__ == "__main__":
    main()
