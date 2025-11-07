# enegic_mqtt

Small Python tool to poll data from the Enegic API and publish it to an MQTT broker.

---

## 🔧 Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 🔄 Running

Both entry points read the same `config.yaml` (or the file pointed to by `ENEGIC_CONFIG_FILE`) for Enegic credentials and MQTT settings.

### MQTT Publisher / Daemon

Continuously polls the API and publishes the latest values to MQTT:

```bash
python -m src.enegic_mqtt.mqtt_publisher
```

This is the module the Docker image launches by default.

### Manual API Client

Fetches the latest packets once, parses them, and prints the results to stdout – handy while developing or inspecting raw values:

```bash
python -m src.enegic_mqtt.enegic_client
```

---

## 🛠️ Docker

Build the image on your Raspberry Pi (or any machine with Docker):

```bash
docker build -t enegic-mqtt .
```

Run the container with your configuration file mounted:

```bash
docker run -d \
  --name enegic-mqtt \
  -v /path/to/config.yaml:/config/config.yaml:ro \
  -e ENEGIC_CONFIG_FILE=/config/config.yaml \
  enegic-mqtt
```

---

## ⚙️ Example `config.yaml`

```yaml
enegic:
  token: "YOUR_ENEGIC_API_TOKEN"
  site_id: 1724866924847
  poll_interval: 30
  timeout: 10

mqtt:
  host: 192.168.3.233
  port: 1883
  topic_prefix: "enegic"
  qos: 0
  retain: false
  username: "mqtt_user"     # optional
  password: "mqtt_password" # optional
```

**Explanation:**

* `token`: Enegic API token from [https://api.enegic.com](https://api.enegic.com)
* `site_id`: numeric site ID from your account
* `poll_interval`: seconds between API requests
* `topic_prefix`: root topic for MQTT publications (e.g. `enegic/<site_id>/...`)

---

## 📊 Data Flow Overview

```mermaid
graph TD
  A[Enegic API] --> B[Python Script]
  B --> C[MQTT Broker (Mosquitto)]
  C --> D[Telegraf]
  D --> E[InfluxDB]
  E --> F[Grafana]
  E --> G[OpenHAB]
```

**Description:**

1. The Python script polls data from the Enegic API every 30 seconds.
2. Each measurement is published to MQTT under topics like:

   ```
   enegic/1724866924847/phase/realtime/current_L1 2.2
   enegic/1724866924847/phase/realtime/voltage_L1 234.6
   enegic/1724866924847/phase/day/energy 12.34
   ```
3. Telegraf subscribes to all topics (`enegic/#`) and writes values into InfluxDB.
4. Grafana and OpenHAB visualize or automate based on the same dataset.

---

## 🔢 Example Telegraf Config

```toml
[[inputs.mqtt_consumer]]
  servers = ["tcp://mqtt:1883"]
  topics = ["enegic/#"]
  data_format = "value"
  data_type = "float"
  name_override = "enegic"

[[outputs.influxdb]]
  urls = ["http://influx:8086"]
  database = "energy"
```

> 💡 Telegraf works with both **InfluxDB 1.x and 2.x**; configuration differs only in the output plugin (for 2.x use `[[outputs.influxdb_v2]]`).

---

## 📈 Grafana / OpenHAB Integration

* **Grafana:** visualize current, voltage, power, and phase data.
* **OpenHAB:** consume MQTT topics for automations or monitoring.

Example OpenHAB item:

```ini
Number EnCurrentL1 "Current L1 [%.2f A]" { channel="mqtt:topic:enegic:current_L1" }
```

---

## 🧩 MQTT Topic Structure

```
enegic/<site_id>/phase/realtime/current_L1
enegic/<site_id>/phase/realtime/current_L2
enegic/<site_id>/phase/realtime/current_L3
enegic/<site_id>/phase/realtime/voltage_L1
enegic/<site_id>/phase/realtime/voltage_L2
enegic/<site_id>/phase/realtime/voltage_L3
enegic/<site_id>/phase/realtime/power_total
enegic/<site_id>/phase/day/energy
enegic/<site_id>/device/temperature
enegic/<site_id>/device/status
```

---

## 🛂 Persistence & Backups

Persistence and backup depend on your chosen InfluxDB setup.

* Data is usually stored in `/srv/data/influxdb/`.
* The provided `ha-backup.sh` script performs daily local and offsite backups.

---

## 🧭 Monitoring & Troubleshooting

### 🔍 Logs

* **Python script:** Logs to stdout and Docker logs.

  ```bash
  docker logs -f enegic-mqtt
  ```

  Typical entries:

  * Successful API polling cycles
  * MQTT publish confirmations
  * Connection or timeout errors

* **Telegraf:**

  ```bash
  docker logs -f telegraf
  ```

  Shows connection status to MQTT and InfluxDB.

### 🧠 Debugging MQTT traffic

Use **MQTT Explorer** or `mosquitto_sub` to inspect live data:

```bash
mosquitto_sub -h 192.168.3.233 -t 'enegic/#' -v
```

Expected output:

```
enegic/1724866924847/phase/realtime/current_L1 2.3
enegic/1724866924847/phase/realtime/voltage_L2 231.7
```

### 📈 Verifying Influx Writes

List latest measurements:

```bash
influx -database 'energy' -execute 'SELECT * FROM enegic ORDER BY time DESC LIMIT 5'
```

### 🧰 Common Issues

| Symptom             | Likely Cause                        | Fix                                         |
| ------------------- | ----------------------------------- | ------------------------------------------- |
| No MQTT messages    | Wrong broker address or credentials | Check MQTT host/port in `config.yaml`       |
| Telegraf errors     | MQTT not reachable or wrong topic   | Verify topics and Docker network            |
| Influx not updating | Wrong database or output plugin     | Confirm `outputs.influxdb` vs `influxdb_v2` |
| Data gaps           | Script stopped or API timeout       | Check `docker ps` and logs                  |

---

## 📜 License

MIT License
(c) 2025 Florian Wunderle
