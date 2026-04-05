"""LG Air Conditioner — ThinQ Connect (PAT-based) only."""

from __future__ import annotations

import base64
import uuid
from typing import Any

import requests

from iotcli.core.registry import register_protocol
from iotcli.protocols.base import BaseProtocol, ProtocolMeta

_API_KEY = "v6GFvkweNo7DK7yD3ylIZ9w52aKBU0eJ7wLXkSR3"
_CLIENT_ID_PREFIX = "thinq-open-"

_REGION_HOSTS = {
    "KR": "api-kic.lgthinq.com",
    "US": "api-uic.lgthinq.com",
    "CA": "api-uic.lgthinq.com",
}


def _api_base(country: str) -> str:
    host = _REGION_HOSTS.get(country.upper(), "api-eic.lgthinq.com")
    return f"https://{host}"


@register_protocol("lgac")
class LGACProtocol(BaseProtocol):

    meta = ProtocolMeta(
        name="lgac",
        display_name="LG Air Conditioner (ThinQ Connect)",
        default_port=443,
        required_credentials=["pat_token", "device_id"],
        capabilities=["on", "off", "status", "set"],
        is_cloud=True,
        setup_guide=(
            "Get a Personal Access Token (PAT):\n"
            "  1. Open https://connect-pat.lgthinq.com\n"
            "  2. Log in with your LG account\n"
            "  3. My Page -> Personal Access Tokens -> Create\n"
            "  4. Copy the token (valid 90 days)"
        ),
        settable_properties=["temperature", "mode", "fan_speed"],
    )

    def __init__(self, device_config: dict[str, Any], **kw):
        super().__init__(device_config, **kw)
        self.pat_token: str = device_config.get("pat_token", "")
        self.device_id: str | None = device_config.get("device_id")
        self.country: str = (device_config.get("country") or "GB").upper()
        self.session: requests.Session | None = None

        if not self.pat_token:
            raise ValueError("LG AC requires a PAT token from connect-pat.lgthinq.com")
        if not self.device_id:
            raise ValueError("LG AC requires a device_id")

    def connect(self) -> bool:
        try:
            self.session = requests.Session()
            client_id = f"{_CLIENT_ID_PREFIX}{uuid.uuid4().hex[:12]}"
            self.session.headers.update({
                "Authorization": f"Bearer {self.pat_token}",
                "x-country": self.country,
                "x-client-id": client_id,
                "x-api-key": _API_KEY,
                "x-service-phase": "OP",
                "Accept": "application/json",
                "Content-Type": "application/json",
            })
            return True
        except Exception:
            return False

    def disconnect(self) -> None:
        if self.session:
            self.session.close()
            self.session = None

    def _request(self, method: str, path: str, body: dict | None = None) -> dict | None:
        if not self.session:
            return None
        url = f"{_api_base(self.country)}{path}"
        msg_id = base64.urlsafe_b64encode(uuid.uuid4().bytes)[:-2].decode()
        self.session.headers["x-message-id"] = msg_id
        try:
            if method == "GET":
                r = self.session.get(url, timeout=10)
            else:
                headers = {"x-conditional-control": "true"} if method == "POST" else {}
                r = self.session.request(method, url, json=body, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                return data.get("response", data)
            return None
        except Exception:
            return None

    def turn_on(self) -> bool:
        r = self._request(
            "POST",
            f"/devices/{self.device_id}/control",
            {"operation": {"airConOperationMode": "POWER_ON"}},
        )
        return r is not None

    def turn_off(self) -> bool:
        r = self._request(
            "POST",
            f"/devices/{self.device_id}/control",
            {"operation": {"airConOperationMode": "POWER_OFF"}},
        )
        return r is not None

    def get_status(self) -> dict[str, Any]:
        r = self._request("GET", f"/devices/{self.device_id}/state")
        if not r:
            return {"online": False, "error": "No response from ThinQ Connect"}
        op = r.get("operation", {})
        temp = r.get("temperature", {})
        return {
            "online": True,
            "power": op.get("airConOperationMode", "unknown"),
            "mode": r.get("airConJobMode", {}).get("currentJobMode", "unknown"),
            "fan_speed": r.get("airFlow", {}).get("windStrength", "unknown"),
            "current_temp": temp.get("currentTemperature"),
            "target_temp": temp.get("targetTemperature"),
        }

    def set_value(self, property_name: str, value: Any) -> bool:
        payload_map: dict[str, dict] = {
            "temperature": {"temperatureInUnits": {"targetTemperatureC": value, "unit": "C"}},
            "mode": {"airConJobMode": {"currentJobMode": str(value).upper()}},
            "fan_speed": {"airFlow": {"windStrength": str(value).upper()}},
        }
        payload = payload_map.get(property_name)
        if not payload:
            return False
        r = self._request("POST", f"/devices/{self.device_id}/control", payload)
        return r is not None
