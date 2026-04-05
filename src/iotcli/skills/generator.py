"""Skill generator — creates AI-readable skill files from device config + protocol metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from iotcli.config.manager import ConfigManager
from iotcli.core.device import Device
from iotcli.core.registry import protocol_registry
from iotcli.skills.engine import render


class SkillGenerator:
    """Generates AI agent skill files for configured devices."""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.skills_dir = config.config_dir / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    # -- public API -----------------------------------------------------------

    def generate_all(self, output_dir: str | None = None) -> list[str]:
        """Generate skill files for all devices + global skill + system prompt."""
        out = Path(output_dir) if output_dir else self.skills_dir
        out.mkdir(parents=True, exist_ok=True)

        devices = self.config.get_all_devices()
        results: list[str] = []

        # Per-device skills
        for name, device in devices.items():
            path = self._write_device_skill(device, out)
            results.append(str(path))

        # Global skill file
        path = self._write_global_skill(devices, out)
        results.append(str(path))

        # System prompt
        path = self._write_system_prompt(devices, out)
        results.append(str(path))

        return results

    def generate_device_skill(self, device: Device, output_dir: str | None = None) -> str:
        """Generate skill file for a single device."""
        out = Path(output_dir) if output_dir else self.skills_dir
        out.mkdir(parents=True, exist_ok=True)
        return str(self._write_device_skill(device, out))

    def list_skills(self) -> list[str]:
        """List generated skill files."""
        if not self.skills_dir.exists():
            return []
        return sorted(str(p.name) for p in self.skills_dir.iterdir() if p.is_file())

    def get_skill_content(self, device_name: str) -> str | None:
        """Read a device skill file, or None if not found."""
        path = self.skills_dir / f"{device_name}.skill.md"
        if path.exists():
            return path.read_text()
        return None

    # -- internal -------------------------------------------------------------

    def _device_context(self, device: Device) -> dict[str, Any]:
        """Build template context for a device."""
        cls = protocol_registry.get(device.protocol)
        meta = cls.meta if cls and hasattr(cls, "meta") else None

        capabilities = meta.capabilities if meta else ["on", "off", "status", "set"]
        settable = list(meta.settable_properties) if meta else []
        actions: dict[str, str] = {}

        # Enrich with Tuya profile data if applicable
        if device.protocol in ("tuya", "petfeeder"):
            try:
                from iotcli.protocols.tuya import TUYA_PROFILES
                profile_name = device.profile or "generic"
                profile_cls = TUYA_PROFILES.get(profile_name)
                if profile_cls:
                    profile = profile_cls()
                    settable = profile.settable
                    actions = profile.actions
            except Exception:
                pass

        # Infer status fields from protocol
        status_fields = ["online", "power"]
        if device.protocol == "lgac":
            status_fields.extend(["mode", "fan_speed", "current_temp", "target_temp"])
        elif device.profile == "petfeeder":
            status_fields.extend(["battery", "charging", "feed_state", "slow_feed", "light"])
        elif device.protocol == "miio":
            status_fields.extend(["temperature", "humidity", "brightness"])

        return {
            "device": device,
            "meta": meta,
            "capabilities": capabilities,
            "settable_properties": settable,
            "actions": actions,
            "status_fields": status_fields,
        }

    def _write_device_skill(self, device: Device, out_dir: Path) -> Path:
        ctx = self._device_context(device)
        content = render("device_skill.md.j2", **ctx)
        path = out_dir / f"{device.name}.skill.md"
        path.write_text(content)
        return path

    def _write_global_skill(self, devices: dict[str, Device], out_dir: Path) -> Path:
        device_contexts = []
        for name, dev in devices.items():
            ctx = self._device_context(dev)
            device_contexts.append({
                "name": dev.name,
                "protocol": dev.protocol,
                "ip": dev.ip,
                "profile": dev.profile,
                "capabilities": ctx["capabilities"],
                "settable_properties": ctx["settable_properties"],
                "actions": ctx["actions"],
            })
        content = render("_base.yaml.j2", devices=device_contexts)
        path = out_dir / "iotcli.skill.yaml"
        path.write_text(content)
        return path

    def _write_system_prompt(self, devices: dict[str, Device], out_dir: Path) -> Path:
        device_contexts = []
        for name, dev in devices.items():
            ctx = self._device_context(dev)
            device_contexts.append({
                "name": dev.name,
                "protocol": dev.protocol,
                "ip": dev.ip,
                "profile": dev.profile,
                "settable_properties": ctx["settable_properties"],
                "actions": ctx["actions"],
            })
        content = render("system_prompt.md.j2", devices=device_contexts)
        path = out_dir / "system_prompt.md"
        path.write_text(content)
        return path
