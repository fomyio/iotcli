"""Device model — the single source of truth for what a device looks like."""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field, asdict
from typing import Any


def slugify(name: str) -> str:
    """Convert a display name to a CLI-safe slug: lowercase, hyphens, no spaces."""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


class DeviceStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DISCOVERED = "discovered"
    CONFIGURED = "configured"
    UNKNOWN = "unknown"


@dataclass
class Device:
    """Represents a configured IoT device."""

    name: str
    protocol: str
    ip: str
    port: int
    status: DeviceStatus = DeviceStatus.CONFIGURED
    device_id: str | None = None
    profile: str | None = None          # e.g. "petfeeder", "light" for Tuya sub-types
    country: str | None = None          # regional code for cloud protocols (LG)
    device_type: str | None = None      # e.g. "esphome", "tasmota" for HTTP
    topic_prefix: str | None = None     # MQTT topic prefix
    version: str | None = None          # protocol version e.g. "3.4" for Tuya
    extra: dict[str, Any] = field(default_factory=dict)

    # --- credentials are NEVER serialized to devices.yaml ---
    # They live in the encrypted vault and are injected at runtime.
    credentials: dict[str, str] = field(default_factory=dict, repr=False)

    def to_config(self) -> dict[str, Any]:
        """Serialize to the dict stored in devices.yaml (no secrets)."""
        d: dict[str, Any] = {
            "name": self.name,
            "protocol": self.protocol,
            "ip": self.ip,
            "port": self.port,
            "status": self.status.value,
        }
        if self.device_id:
            d["device_id"] = self.device_id
        if self.profile:
            d["profile"] = self.profile
        if self.country:
            d["country"] = self.country
        if self.device_type:
            d["device_type"] = self.device_type
        if self.topic_prefix:
            d["topic_prefix"] = self.topic_prefix
        if self.version:
            d["version"] = self.version
        if self.extra:
            d["extra"] = self.extra
        return d

    @classmethod
    def from_config(cls, data: dict[str, Any], credentials: dict[str, str] | None = None) -> Device:
        """Hydrate from a devices.yaml entry + optional vault credentials."""
        return cls(
            name=data["name"],
            protocol=data["protocol"],
            ip=data.get("ip", "0.0.0.0"),
            port=data.get("port", 0),
            status=DeviceStatus(data.get("status", "configured")),
            device_id=data.get("device_id"),
            profile=data.get("profile"),
            country=data.get("country"),
            device_type=data.get("device_type"),
            topic_prefix=data.get("topic_prefix"),
            version=data.get("version"),
            extra=data.get("extra", {}),
            credentials=credentials or {},
        )

    def merge_dict(self) -> dict[str, Any]:
        """Flat dict with credentials injected — used to instantiate protocol handlers."""
        d = self.to_config()
        d.update(self.credentials)
        return d
