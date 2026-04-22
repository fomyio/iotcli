"""Tuya protocol — supports generic devices + named profiles (petfeeder, light, switch).

Adding a new device type = adding a TuyaProfile subclass below. Nothing else changes.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import tinytuya

from iotcli.core.registry import register_protocol
from iotcli.protocols.base import BaseProtocol, ProtocolMeta, Property


# ── Tuya device profiles ────────────────────────────────────────────────────


class TuyaProfile:
    """Base profile — maps human-friendly names to Tuya DPS ids."""

    name = "generic"
    description = "Generic Tuya device"

    # Override in subclasses: {"friendly_name": dps_id}
    dps_map: dict[str, int] = {"power": 1}

    # Override to expose custom high-level actions
    actions: dict[str, str] = {}  # {"action_name": "description"}

    # Override to list settable property names for skill generation
    settable: list[str] = ["power"]

    # Rich typed properties — preferred over `settable`. When provided, the skill
    # generator emits type/enum/range info; otherwise it falls back to `settable`.
    properties: list[Property] = [
        Property(name="power", type="enum", enum=["on", "off"], description="Power state."),
    ]
    status_properties: list[Property] = [
        Property(name="online", type="bool", settable=False),
        Property(name="power", type="enum", enum=["on", "off", "unknown"], settable=False),
    ]

    def interpret_status(self, dps: dict[int, Any]) -> dict[str, Any]:
        """Convert raw DPS to human-readable status dict."""
        status: dict[str, Any] = {"online": True, "dps": dps}
        if 1 in dps:
            status["power"] = "on" if dps[1] else "off"
        return status

    def map_set(self, prop: str, value: Any) -> tuple[int, Any] | None:
        """Map a named property to (dps_id, value). Return None if unknown."""
        dp_id = self.dps_map.get(prop)
        if dp_id is not None:
            return dp_id, value
        try:
            return int(prop), value
        except ValueError:
            return None

    def custom_action(self, action: str, value: Any, protocol: "TuyaProtocol") -> bool:
        """Handle profile-specific actions. Return False if not handled."""
        return False


class LightProfile(TuyaProfile):
    name = "light"
    description = "Tuya smart light / bulb"
    dps_map = {"power": 1, "brightness": 2, "color_temperature": 3, "mode": 4, "color": 5}
    settable = ["power", "brightness", "color_temperature", "mode", "color"]
    properties = [
        Property(name="power", type="enum", enum=["on", "off"], description="Power state."),
        Property(
            name="brightness",
            type="int",
            description="Brightness level (Tuya raw scale, typically 10-1000).",
            minimum=10,
            maximum=1000,
            example=500,
        ),
        Property(
            name="color_temperature",
            type="int",
            description="Color temperature (Tuya raw scale, typically 0-1000).",
            minimum=0,
            maximum=1000,
            example=500,
        ),
        Property(
            name="mode",
            type="enum",
            description="Bulb mode.",
            enum=["white", "colour", "scene", "music"],
        ),
        Property(
            name="color",
            type="str",
            description="Color as a Tuya HSV hex string (12 hex chars).",
            example="0084007003e8",
        ),
    ]
    status_properties = [
        Property(name="online", type="bool", settable=False),
        Property(name="power", type="enum", enum=["on", "off", "unknown"], settable=False),
        Property(name="brightness", type="int", settable=False),
        Property(name="color_temperature", type="int", settable=False),
    ]


class SwitchProfile(TuyaProfile):
    name = "switch"
    description = "Tuya smart plug / switch"
    dps_map = {"power": 1, "countdown": 2}
    settable = ["power", "countdown"]
    properties = [
        Property(name="power", type="enum", enum=["on", "off"], description="Power state."),
        Property(
            name="countdown",
            type="int",
            description="Auto-off countdown in seconds (0 disables).",
            minimum=0,
            maximum=86400,
            unit="s",
            example=300,
        ),
    ]
    status_properties = [
        Property(name="online", type="bool", settable=False),
        Property(name="power", type="enum", enum=["on", "off", "unknown"], settable=False),
        Property(name="countdown", type="int", unit="s", settable=False),
    ]


class PetFeederProfile(TuyaProfile):
    name = "petfeeder"
    description = "Tuya-based pet feeder (e.g. ROJECO)"

    DP_MEAL_PLAN = 1
    DP_QUICK_FEED = 2
    DP_MANUAL_FEED = 3
    DP_FEED_STATE = 4
    DP_BATTERY = 10
    DP_CHARGING = 11
    DP_FAULT = 13
    DP_FEED_REPORT = 14
    DP_LIGHT = 17
    DP_SLOW_FEED = 23

    dps_map = {
        "meal_plan": 1,
        "quick_feed": 2,
        "portions": 3,
        "feed_state": 4,
        "battery": 10,
        "charging": 11,
        "fault": 13,
        "feed_report": 14,
        "light": 17,
        "slow_feed": 23,
    }

    actions = {
        "quick_feed": "Trigger an immediate single-portion feed (no value).",
        "portions": "Dispense N portions immediately (1-60).",
    }

    settable = ["portions", "quick_feed", "slow_feed", "light"]

    properties = [
        Property(
            name="portions",
            type="int",
            description="Dispense this many portions immediately.",
            minimum=1,
            maximum=60,
            example=2,
        ),
        Property(
            name="quick_feed",
            type="trigger",
            description="Trigger one quick feed (no value needed — pass `true`).",
            example=True,
        ),
        Property(
            name="slow_feed",
            type="bool",
            description="Enable slow-feed mode (drops portions over a longer interval).",
        ),
        Property(
            name="light",
            type="bool",
            description="Enable the indicator light on the feeder.",
        ),
    ]
    status_properties = [
        Property(name="online", type="bool", settable=False),
        Property(name="battery", type="int", unit="%", description="Battery percentage.", settable=False),
        Property(name="charging", type="bool", description="Whether the feeder is charging.", settable=False),
        Property(name="feed_state", type="int", description="Internal feed state code.", settable=False),
        Property(name="last_feed_amount", type="int", description="Portions in the most recent feed.", settable=False),
        Property(name="slow_feed", type="bool", settable=False),
        Property(name="light", type="bool", settable=False),
        Property(name="meal_plan", type="str", description="Programmed meal schedule (raw).", settable=False),
        Property(name="food_empty", type="bool", description="True if food hopper is empty.", settable=False),
    ]

    def interpret_status(self, dps: dict[int, Any]) -> dict[str, Any]:
        s: dict[str, Any] = {"online": True, "dps": dps}
        field_map = {
            self.DP_BATTERY: "battery",
            self.DP_CHARGING: "charging",
            self.DP_FEED_STATE: "feed_state",
            self.DP_FEED_REPORT: "last_feed_amount",
            self.DP_SLOW_FEED: "slow_feed",
            self.DP_LIGHT: "light",
            self.DP_MEAL_PLAN: "meal_plan",
        }
        for dp_id, key in field_map.items():
            if dp_id in dps:
                s[key] = dps[dp_id]
        if self.DP_FAULT in dps and dps[self.DP_FAULT]:
            s["fault"] = dps[self.DP_FAULT]
            if dps[self.DP_FAULT] & 2:
                s["food_empty"] = True
        return s

    def custom_action(self, action: str, value: Any, protocol: "TuyaProtocol") -> bool:
        if action == "quick_feed":
            return protocol._control_dp(self.DP_QUICK_FEED, True)
        if action in ("portions", "manual_feed"):
            n = int(value)
            if not 1 <= n <= 60:
                return False
            return protocol._control_dp(self.DP_MANUAL_FEED, n)
        return False


# Profile registry
TUYA_PROFILES: dict[str, type[TuyaProfile]] = {
    "generic": TuyaProfile,
    "light": LightProfile,
    "switch": SwitchProfile,
    "petfeeder": PetFeederProfile,
}


# ── Protocol implementation ──────────────────────────────────────────────────


@register_protocol("tuya", aliases=["petfeeder"])
class TuyaProtocol(BaseProtocol):

    meta = ProtocolMeta(
        name="tuya",
        display_name="Tuya",
        default_port=6668,
        required_credentials=["device_id", "local_key"],
        capabilities=["on", "off", "status", "set"],
        setup_guide=(
            "Get your device_id and local_key:\n"
            "  1. pip install tinytuya && python -m tinytuya wizard\n"
            "  2. Or use the Tuya IoT Platform at iot.tuya.com"
        ),
        profiles={p.name: p.description for p in [cls() for cls in TUYA_PROFILES.values()]},
        settable_properties=["power", "brightness", "color_temperature", "portions"],
    )

    def __init__(self, device_config: dict[str, Any], **kw):
        super().__init__(device_config, **kw)
        self.device_id: str = device_config.get("device_id", "")
        self.local_key: str = device_config.get("local_key", "")
        self.version: float = float(device_config.get("version", "3.3"))
        self._tuya: tinytuya.Device | None = None

        if not self.device_id:
            raise ValueError("Tuya device_id is required")
        if not self.local_key:
            raise ValueError("Tuya local_key is required")

        # Resolve profile
        profile_name = device_config.get("profile", "generic")
        # "petfeeder" protocol alias → auto-select petfeeder profile
        if device_config.get("protocol") == "petfeeder" and profile_name == "generic":
            profile_name = "petfeeder"
        profile_cls = TUYA_PROFILES.get(profile_name, TuyaProfile)
        self.profile: TuyaProfile = profile_cls()

    def connect(self) -> bool:
        try:
            self._tuya = tinytuya.Device(
                dev_id=self.device_id,
                address=self.ip,
                local_key=self.local_key,
                version=self.version,
            )
            return True
        except Exception as e:
            if self.debug:
                logging.getLogger(__name__).debug(f"Tuya connect error: {e}")
            return False

    def disconnect(self) -> None:
        if self._tuya:
            try:
                self._tuya.close()
            except Exception:
                pass
            self._tuya = None

    def turn_on(self) -> bool:
        if not self._tuya:
            return False
        # Pet feeder "on" = quick feed
        if self.profile.name == "petfeeder":
            return self.profile.custom_action("quick_feed", True, self)
        try:
            return self._ok(self._tuya.turn_on())
        except Exception:
            return False

    def turn_off(self) -> bool:
        if not self._tuya:
            return False
        if self.profile.name == "petfeeder":
            return True  # no off state for feeder
        try:
            return self._ok(self._tuya.turn_off())
        except Exception:
            return False

    def get_status(self) -> dict[str, Any]:
        if not self._tuya:
            return {"online": False, "error": "Not connected"}
        try:
            data = self._tuya.status()
            if data and "dps" in data:
                dps = self._normalize_dps(data["dps"])
                return self.profile.interpret_status(dps)
            if data and "Error" in data:
                return {"online": False, "error": data.get("Payload") or data["Error"]}
            return {"online": False, "error": "No response"}
        except Exception as e:
            return {"online": False, "error": str(e)}

    def set_value(self, property_name: str, value: Any) -> bool:
        # Try profile custom action first
        if self.profile.custom_action(property_name, value, self):
            return True
        # Fall back to DPS mapping
        mapped = self.profile.map_set(property_name, value)
        if mapped is None:
            return False
        dp_id, val = mapped
        return self._control_dp(dp_id, val)

    # -- helpers (exposed to profiles) ----------------------------------------

    def _normalize_dps(self, raw: dict) -> dict[int, Any]:
        out: dict[int, Any] = {}
        for k, v in raw.items():
            try:
                out[int(k)] = v
            except (ValueError, TypeError):
                pass
        return out

    def _control_dp(self, dp_id: int, value: Any) -> bool:
        if not self._tuya:
            return False
        try:
            return self._ok(self._tuya.set_value(dp_id, value))
        except Exception:
            return False

    @staticmethod
    def _ok(result) -> bool:
        if result is None:
            return False
        if isinstance(result, dict) and "Error" in result:
            return False
        return True
