"""HTTP protocol — ESPHome, Tasmota, and generic HTTP devices."""

from __future__ import annotations

from typing import Any

import requests

from iotcli.core.registry import register_protocol
from iotcli.protocols.base import BaseProtocol, ProtocolMeta


@register_protocol("http")
class HTTPProtocol(BaseProtocol):

    meta = ProtocolMeta(
        name="http",
        display_name="HTTP (ESPHome / Tasmota)",
        default_port=80,
        required_credentials=[],
        capabilities=["on", "off", "status", "set"],
        setup_guide="Just provide the device IP. No credentials needed for most HTTP devices.",
        settable_properties=["power", "brightness", "color"],
    )

    def __init__(self, device_config: dict[str, Any], **kw):
        super().__init__(device_config, **kw)
        self.base_url = f"http://{self.ip}:{self.port}"
        self.device_type: str = device_config.get("device_type", "generic")
        self.session: requests.Session | None = None

    def connect(self) -> bool:
        try:
            self.session = requests.Session()
            self.session.timeout = 5
            r = self.session.get(f"{self.base_url}/", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def disconnect(self) -> None:
        if self.session:
            self.session.close()
            self.session = None

    def turn_on(self) -> bool:
        return self._power("ON")

    def turn_off(self) -> bool:
        return self._power("OFF")

    def _power(self, state: str) -> bool:
        if not self.session:
            return False
        try:
            if self.device_type == "tasmota":
                r = self.session.get(f"{self.base_url}/cm", params={"cmnd": f"Power {state}"})
                return r.status_code == 200
            if self.device_type == "esphome":
                action = "turn_on" if state == "ON" else "turn_off"
                r = self.session.post(f"{self.base_url}/switch/{action}")
                return r.status_code == 200
            # generic — try common endpoints
            for ep in (f"/api/turn_{state.lower()}", f"/control?state={state.lower()}", f"/{state.lower()}"):
                try:
                    r = self.session.get(f"{self.base_url}{ep}", timeout=3)
                    if r.status_code == 200:
                        return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    def get_status(self) -> dict[str, Any]:
        if not self.session:
            return {"online": False, "error": "Not connected"}
        try:
            if self.device_type == "tasmota":
                r = self.session.get(f"{self.base_url}/cm", params={"cmnd": "Status"})
                if r.status_code == 200:
                    data = r.json()
                    s = data.get("Status", {})
                    return {
                        "online": True,
                        "power": s.get("Power", "unknown"),
                        "device_name": s.get("DeviceName", self.device_name),
                        "model": s.get("Module", "unknown"),
                    }
            elif self.device_type == "esphome":
                r = self.session.get(f"{self.base_url}/api/info")
                if r.status_code == 200:
                    data = r.json()
                    return {
                        "online": True,
                        "device_name": data.get("name", self.device_name),
                        "esphome_version": data.get("esphome_version", "unknown"),
                    }
            else:
                r = self.session.get(f"{self.base_url}/", timeout=3)
                if r.status_code == 200:
                    return {"online": True, "raw_response": r.text[:200]}
            return {"online": False, "error": "Bad response"}
        except Exception as e:
            return {"online": False, "error": str(e)}

    def set_value(self, property_name: str, value: Any) -> bool:
        if not self.session:
            return False
        try:
            if self.device_type == "tasmota":
                r = self.session.get(
                    f"{self.base_url}/cm", params={"cmnd": f"{property_name} {value}"}
                )
                return r.status_code == 200
            if self.device_type == "esphome":
                r = self.session.post(
                    f"{self.base_url}/{property_name}/set", json={"value": value}
                )
                return r.status_code == 200
            for ep in (
                f"/api/set?{property_name}={value}",
                f"/control?{property_name}={value}",
            ):
                try:
                    r = self.session.get(f"{self.base_url}{ep}", timeout=3)
                    if r.status_code == 200:
                        return True
                except Exception:
                    continue
            return False
        except Exception:
            return False
