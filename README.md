# enegic_mqtt

Small Python tool to poll data from the Enegic API and publish it to an MQTT broker.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m enegic_mqtt.mqtt_publisher
```

## Docker

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
