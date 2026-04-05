"""MQTT protocol — Zigbee/Aqara devices via MQTT broker."""

from __future__ import annotations

import json
import time
from typing import Any

import paho.mqtt.client as mqtt

from iotcli.core.registry import register_protocol
from iotcli.protocols.base import BaseProtocol, ProtocolMeta


@register_protocol("mqtt")
class MQTTProtocol(BaseProtocol):

    meta = ProtocolMeta(
        name="mqtt",
        display_name="MQTT (Zigbee / Aqara)",
        default_port=1883,
        required_credentials=[],
        optional_credentials=["username", "password"],
        capabilities=["on", "off", "status", "set"],
        setup_guide=(
            "Point to your MQTT broker (e.g. Mosquitto running on a Pi).\n"
            "Credentials are optional — only needed if the broker requires auth."
        ),
        settable_properties=["state", "brightness", "color_temp"],
    )

    def __init__(self, device_config: dict[str, Any], **kw):
        super().__init__(device_config, **kw)
        self.broker_ip: str = device_config.get("broker_ip", self.ip)
        self.broker_port: int = device_config.get("broker_port", self.meta.default_port)
        self.username: str | None = device_config.get("username")
        self.password: str | None = device_config.get("password")
        self.topic_prefix: str = device_config.get("topic_prefix", "zigbee2mqtt")
        self.device_id: str | None = device_config.get("device_id")

        self.client: mqtt.Client | None = None
        self.connected = False
        self.last_status: dict[str, Any] = {}
        self._status_received = False

    # -- callbacks ------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            if self.device_id:
                client.subscribe(f"{self.topic_prefix}/{self.device_id}")
        elif self.debug:
            print(f"MQTT connect failed: rc={rc}")

    def _on_message(self, client, userdata, msg):
        try:
            self.last_status = json.loads(msg.payload.decode())
            self._status_received = True
        except Exception:
            pass

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False

    # -- BaseProtocol ---------------------------------------------------------

    def connect(self) -> bool:
        try:
            self.client = mqtt.Client()
            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            self.client.on_disconnect = self._on_disconnect
            if self.username:
                self.client.username_pw_set(self.username, self.password)
            self.client.connect(self.broker_ip, self.broker_port, 60)
            self.client.loop_start()
            deadline = time.time() + 5
            while not self.connected and time.time() < deadline:
                time.sleep(0.1)
            return self.connected
        except Exception:
            return False

    def disconnect(self) -> None:
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.client = None
            self.connected = False

    def _publish(self, topic: str, payload: dict[str, Any]) -> bool:
        if not self.connected:
            return False
        try:
            result = self.client.publish(topic, json.dumps(payload))
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception:
            return False

    def turn_on(self) -> bool:
        return self._publish(f"{self.topic_prefix}/{self.device_id}/set", {"state": "ON"})

    def turn_off(self) -> bool:
        return self._publish(f"{self.topic_prefix}/{self.device_id}/set", {"state": "OFF"})

    def get_status(self) -> dict[str, Any]:
        self._status_received = False
        self._publish(f"{self.topic_prefix}/{self.device_id}/get", {})
        deadline = time.time() + 3
        while not self._status_received and time.time() < deadline:
            time.sleep(0.1)
        if self._status_received:
            return {"online": True, **self.last_status}
        return {"online": False, "error": "No response"}

    def set_value(self, property_name: str, value: Any) -> bool:
        return self._publish(
            f"{self.topic_prefix}/{self.device_id}/set", {property_name: value}
        )
