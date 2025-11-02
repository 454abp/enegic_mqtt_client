import paho.mqtt.client as mqtt
import time

BROKER = "mqtt.wanninger.454abp.de"    # My MQTT
PORT = 1883
TOPIC = "enegic/test"

# Callback wenn Verbindung aufgebaut ist
def on_connect(client, userdata, flags, rc):
    print("Connected with result code", rc)
    client.subscribe(TOPIC)

# Callback wenn Nachricht empfangen wird
def on_message(client, userdata, msg):
    print(f"Received on {msg.topic}: {msg.payload.decode()}")


def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    print("print", "payload")

    client.connect(BROKER, PORT, keepalive=60)

    client.loop_start()

    try:
        while True:
            payload = f"Hello MQTT! {time.time()}"
            client.publish(TOPIC, payload)
            print("Sent:", payload)
            time.sleep(5)
    except KeyboardInterrupt:
        print("Disconnecting...")
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()

