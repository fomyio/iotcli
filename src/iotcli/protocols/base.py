"""Base protocol class with metadata for auto-registration and skill generation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProtocolMeta:
    """Metadata that every protocol exposes — used by the registry, TUI, and skill generator."""

    name: str
    display_name: str
    default_port: int
    required_credentials: list[str] = field(default_factory=list)
    optional_credentials: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=lambda: ["on", "off", "status", "set"])
    setup_guide: str = ""
    is_cloud: bool = False
    profiles: dict[str, str] = field(default_factory=dict)  # profile_name -> description
    settable_properties: list[str] = field(default_factory=list)


class BaseProtocol(ABC):
    """Abstract base for all IoT protocol handlers."""

    meta: ProtocolMeta  # subclasses MUST define this as a class attribute

    def __init__(
        self,
        device_config: dict[str, Any],
        verbose: bool = False,
        debug: bool = False,
    ):
        self.config = device_config
        self.verbose = verbose
        self.debug = debug
        self.device_name: str = device_config.get("name", "Unknown")
        self.ip: str = device_config.get("ip", "0.0.0.0")
        self.port: int = device_config.get("port", self.meta.default_port)

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection. Returns True on success."""

    @abstractmethod
    def disconnect(self) -> None:
        """Clean up connection resources."""

    @abstractmethod
    def turn_on(self) -> bool:
        """Turn device on. Returns True on success."""

    @abstractmethod
    def turn_off(self) -> bool:
        """Turn device off. Returns True on success."""

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """Return device status dict. Must contain 'online' key."""

    @abstractmethod
    def set_value(self, property_name: str, value: Any) -> bool:
        """Set an arbitrary device property. Returns True on success."""

    def test_connection(self) -> bool:
        """Quick connectivity check."""
        try:
            if self.connect():
                status = self.get_status()
                self.disconnect()
                return status is not None
            return False
        except Exception:
            return False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.disconnect()
