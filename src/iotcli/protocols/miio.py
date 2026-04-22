"""Xiaomi miIO protocol — UDP 54321, AES-128-CBC, token auth."""

from __future__ import annotations

import hashlib
import json
import logging
import socket
import struct
import time
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from iotcli.core.registry import register_protocol
from iotcli.protocols.base import BaseProtocol, ProtocolMeta, Property


# ── miIO device profiles ────────────────────────────────────────────────────


class MiIOProfile:
    """Base profile — describes settable + status properties for a miIO device class."""

    name = "generic"
    description = "Generic Xiaomi miIO device"
    properties: list[Property] = [
        Property(name="power", type="enum", description="Power state.", enum=["on", "off"]),
    ]
    status_properties: list[Property] = [
        Property(name="online", type="bool", settable=False),
        Property(name="power", type="enum", enum=["on", "off", "unknown"], settable=False),
    ]


class BulbProfile(MiIOProfile):
    name = "bulb"
    description = "Xiaomi smart LED bulb / Yeelight"
    properties = [
        Property(name="power", type="enum", enum=["on", "off"], description="Power state."),
        Property(
            name="brightness",
            type="int",
            description="Brightness percentage.",
            minimum=1,
            maximum=100,
            unit="%",
            example=80,
        ),
        Property(
            name="color_temperature",
            type="int",
            description="Color temperature in Kelvin (warm→cool).",
            minimum=1700,
            maximum=6500,
            unit="K",
            example=4000,
        ),
        Property(
            name="color",
            type="str",
            description='RGB color as "r,g,b" or 24-bit integer.',
            example="255,180,90",
        ),
        Property(
            name="mode",
            type="enum",
            description="Operating mode.",
            enum=["day", "night", "color", "hsv", "ct"],
        ),
    ]
    status_properties = [
        Property(name="online", type="bool", settable=False),
        Property(name="power", type="enum", enum=["on", "off", "unknown"], settable=False),
        Property(name="brightness", type="int", unit="%", settable=False),
        Property(name="color_temperature", type="int", unit="K", settable=False),
    ]


class CameraProfile(MiIOProfile):
    name = "camera"
    description = "Xiaomi smart camera"
    properties = [
        Property(name="power", type="enum", enum=["on", "off"], description="Camera power."),
        Property(
            name="motion_detection",
            type="bool",
            description="Enable / disable motion detection.",
        ),
        Property(
            name="night_mode",
            type="enum",
            description="IR night-vision mode.",
            enum=["auto", "on", "off"],
        ),
    ]
    status_properties = [
        Property(name="online", type="bool", settable=False),
        Property(name="power", type="enum", enum=["on", "off", "unknown"], settable=False),
        Property(name="motion_detection", type="bool", settable=False),
    ]


class AirFryerProfile(MiIOProfile):
    name = "airfryer"
    description = "Xiaomi smart air fryer"
    properties = [
        Property(
            name="power",
            type="enum",
            enum=["on", "off"],
            description="Power state — only meaningful between cooks.",
        ),
        Property(
            name="target_temp",
            type="int",
            description="Target cooking temperature.",
            minimum=40,
            maximum=200,
            unit="C",
            example=180,
        ),
        Property(
            name="target_time",
            type="int",
            description="Cooking duration in minutes.",
            minimum=1,
            maximum=1440,
            unit="min",
            example=15,
        ),
        Property(
            name="start",
            type="trigger",
            description="Start the current cooking program.",
        ),
        Property(
            name="pause",
            type="trigger",
            description="Pause an active cooking program.",
        ),
    ]
    status_properties = [
        Property(name="online", type="bool", settable=False),
        Property(name="power", type="enum", enum=["on", "off", "unknown"], settable=False),
        Property(name="target_temp", type="int", unit="C", settable=False),
        Property(name="target_time", type="int", unit="min", settable=False),
        Property(name="status", type="str", description="Current cook state.", settable=False),
    ]


class VacuumProfile(MiIOProfile):
    name = "vacuum"
    description = "Xiaomi/Roborock robot vacuum"
    properties = [
        Property(name="power", type="enum", enum=["on", "off"], description="Cleaning on/off."),
        Property(
            name="fan_speed",
            type="enum",
            description="Suction power.",
            enum=["quiet", "balanced", "turbo", "max"],
        ),
        Property(name="dock", type="trigger", description="Send the vacuum back to its dock."),
    ]
    status_properties = [
        Property(name="online", type="bool", settable=False),
        Property(name="power", type="enum", enum=["on", "off", "unknown"], settable=False),
        Property(name="battery", type="int", unit="%", settable=False),
        Property(name="state", type="str", description="Vacuum state machine.", settable=False),
    ]


# Profile registry
MIIO_PROFILES: dict[str, type[MiIOProfile]] = {
    "generic": MiIOProfile,
    "bulb": BulbProfile,
    "camera": CameraProfile,
    "airfryer": AirFryerProfile,
    "vacuum": VacuumProfile,
}


@register_protocol("miio")
class MiIOProtocol(BaseProtocol):

    meta = ProtocolMeta(
        name="miio",
        display_name="Xiaomi miIO",
        default_port=54321,
        required_credentials=["token"],
        capabilities=["on", "off", "status", "set"],
        setup_guide=(
            "Extract your 32-char hex token using one of:\n"
            "  1. python -m miio cloud login && python -m miio cloud list\n"
            "  2. Xiaomi Cloud Tokens Extractor (pip install xiaomi_tokens)\n"
            "  3. Mi Home app + token extractor GitHub tool"
        ),
        profiles={p.name: p.description for p in [cls() for cls in MIIO_PROFILES.values()]},
        # Generic placeholder — overridden per device via profile in the skill generator.
        settable_properties=["power"],
    )

    MAGIC = 0x2131

    def __init__(self, device_config: dict[str, Any], **kw):
        super().__init__(device_config, **kw)
        self.token: str = device_config.get("token", "")
        self.device_id = device_config.get("device_id", 0xFFFFFFFF)
        if isinstance(self.device_id, str):
            try:
                self.device_id = int(self.device_id)
            except ValueError:
                self.device_id = 0xFFFFFFFF

        if not self.token or len(self.token) != 32:
            raise ValueError("miIO requires a 32-character hex token")

        self.token_bytes = bytes.fromhex(self.token)
        self.key = self._md5(self.token_bytes)
        self.iv = self._md5(self.key + self.token_bytes)

        self.sock: socket.socket | None = None
        self.message_id = 1
        self._stamp: int | None = None
        self._device_ts: int | None = None

    # -- crypto helpers -------------------------------------------------------

    @staticmethod
    def _md5(data: bytes) -> bytes:
        return hashlib.md5(data).digest()

    def _encrypt(self, data: bytes) -> bytes:
        pad_len = 16 - (len(data) % 16)
        padded = data + bytes([pad_len] * pad_len)
        enc = Cipher(algorithms.AES(self.key), modes.CBC(self.iv)).encryptor()
        return enc.update(padded) + enc.finalize()

    def _decrypt(self, data: bytes) -> bytes:
        dec = Cipher(algorithms.AES(self.key), modes.CBC(self.iv)).decryptor()
        plain = dec.update(data) + dec.finalize()
        return plain[: -plain[-1]]

    # -- packet helpers -------------------------------------------------------

    def _build_packet(self, payload: bytes) -> bytes:
        encrypted = self._encrypt(payload)
        msg_id = self._stamp if self._stamp is not None else self.message_id
        ts = (self._device_ts + 1) if self._device_ts is not None else int(time.time())
        length = 32 + len(encrypted)
        header = struct.pack(">HHIII", self.MAGIC, length, 0, msg_id, ts)
        checksum = self._md5(header + self.token_bytes + encrypted)
        self.message_id += 1
        return header + checksum + encrypted

    def _parse_packet(self, data: bytes) -> dict[str, Any] | None:
        if len(data) < 32:
            return None
        magic, length, dev_id, msg_id, ts = struct.unpack(">HHIII", data[:16])
        if magic != self.MAGIC:
            return None
        checksum = data[16:32]
        encrypted = data[32:]
        expected = self._md5(data[:16] + self.token_bytes + encrypted)
        if checksum != expected:
            return None
        try:
            return json.loads(self._decrypt(encrypted))
        except Exception:
            return None

    def _send_command(self, method: str, params: Any = None) -> dict[str, Any] | None:
        if not self.sock:
            return None
        cmd: dict[str, Any] = {"id": self.message_id, "method": method}
        if params is not None:
            cmd["params"] = params
        packet = self._build_packet(json.dumps(cmd).encode())
        self.sock.sendto(packet, (self.ip, self.port))
        data, _ = self.sock.recvfrom(4096)
        return self._parse_packet(data)

    # -- BaseProtocol ---------------------------------------------------------

    def connect(self) -> bool:
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(5)
            hello = bytes.fromhex(
                "21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
            )
            self.sock.sendto(hello, (self.ip, self.port))
            data, _ = self.sock.recvfrom(1024)
            if len(data) >= 32:
                _, _, _, stamp, ts = struct.unpack(">HHIII", data[:16])
                self._stamp = stamp
                self._device_ts = ts
                return True
            return False
        except Exception as e:
            if self.debug:
                print(f"miIO connect error: {e}")
            return False

    def disconnect(self) -> None:
        if self.sock:
            self.sock.close()
            self.sock = None

    def turn_on(self) -> bool:
        r = self._send_command("set_power", ["on"])
        return bool(r and r.get("result", [None])[0] == "ok")

    def turn_off(self) -> bool:
        r = self._send_command("set_power", ["off"])
        return bool(r and r.get("result", [None])[0] == "ok")

    def get_status(self) -> dict[str, Any]:
        r = self._send_command("get_prop", ["power"])
        if not r or "result" not in r:
            return {"online": False, "error": "No response"}
        result = r["result"]
        status: dict[str, Any] = {"online": True, "power": result[0] if result else "unknown"}
        # try extra properties (not all devices support them)
        try:
            extra = self._send_command("get_prop", ["temperature", "humidity", "brightness"])
            if extra and "result" in extra:
                er = extra["result"]
                for i, key in enumerate(("temperature", "humidity", "brightness")):
                    if i < len(er) and er[i] not in (None, "unknow", ""):
                        status[key] = er[i]
        except Exception:
            pass
        return status

    def set_value(self, property_name: str, value: Any) -> bool:
        method_map = {
            "brightness": "set_bright",
            "color_temperature": "set_ct_abx",
            "color": "set_rgb",
            "mode": "set_mode",
        }
        method = method_map.get(property_name, f"set_{property_name}")
        r = self._send_command(method, [value])
        return bool(r and r.get("result") == ["ok"])
