"""Configuration manager — devices.yaml + credential vault."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from iotcli.config.credentials import CredentialVault, SENSITIVE_FIELDS
from iotcli.core.device import Device, DeviceStatus, slugify
from iotcli.core.exceptions import DeviceNotFoundError


class ConfigManager:
    """Manages device configuration (YAML) and encrypted credentials (vault)."""

    def __init__(self, config_dir: str | Path | None = None):
        self.config_dir = Path(config_dir) if config_dir else Path.home() / ".iotcli"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / "devices.yaml"
        self.vault = CredentialVault(self.config_dir)
        self._data: dict[str, Any] = self._load()

    # -- persistence ----------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        if self.config_file.exists():
            try:
                return yaml.safe_load(self.config_file.read_text()) or {}
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        self.config_file.write_text(yaml.dump(self._data, default_flow_style=False))

    # -- device CRUD ----------------------------------------------------------

    def add_device(self, device: Device | dict[str, Any]) -> bool:
        """Add or update a device. Accepts Device or raw dict (from wizard)."""
        if isinstance(device, dict):
            raw = device
            name = slugify(raw["name"])
            raw["name"] = name
            # extract and vault secrets
            secrets = CredentialVault.extract_secrets(raw)
            if secrets:
                self.vault.save(name, secrets)
            # strip secrets from config dict
            clean = {k: v for k, v in raw.items() if k not in SENSITIVE_FIELDS}
            self._data.setdefault("devices", {})[name] = clean
        else:
            name = slugify(device.name)
            device.name = name
            if device.credentials:
                self.vault.save(name, device.credentials)
            self._data.setdefault("devices", {})[name] = device.to_config()

        self._save()
        return True

    def remove_device(self, name: str) -> bool:
        devices = self._data.get("devices", {})
        if name not in devices:
            return False
        del devices[name]
        self.vault.delete(name)
        self._save()
        return True

    def get_device(self, name: str) -> Device:
        """Get a single device with credentials injected."""
        devices = self._data.get("devices", {})
        raw = devices.get(name)
        if raw is None:
            raise DeviceNotFoundError(name)
        creds = self.vault.load(name)
        return Device.from_config(raw, credentials=creds)

    def get_device_or_none(self, name: str) -> Device | None:
        try:
            return self.get_device(name)
        except DeviceNotFoundError:
            return None

    def get_all_devices(self) -> dict[str, Device]:
        """Return all devices with credentials injected."""
        out: dict[str, Device] = {}
        for name, raw in self._data.get("devices", {}).items():
            creds = self.vault.load(name)
            out[name] = Device.from_config(raw, credentials=creds)
        return out

    def update_status(self, name: str, status: DeviceStatus) -> None:
        devices = self._data.get("devices", {})
        if name in devices:
            devices[name]["status"] = status.value
            self._save()

    def device_names(self) -> list[str]:
        return list(self._data.get("devices", {}).keys())

    def device_count(self) -> int:
        return len(self._data.get("devices", {}))
