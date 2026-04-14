"""Skill generator — creates AI-readable skill files from device config + protocol metadata.

Always writes per-device skill directories:

- `skills/<device-slug>/SKILL.md` — an OpenClaw-compatible per-device skill (one directory
  per device, frontmatter `name`/`description`/`metadata` so agent loaders can pick it up).

When writing to the canonical default directory (`~/.iotcli/skills/`) three additional
admin/back-compat files are also emitted:

- `skills/iotcli.tools.json` — OpenAI/Anthropic-compatible tool schema for the iotcli CLI.
- `skills/iotcli.skill.yaml` — legacy global skill YAML kept for back-compat.
- `skills/system_prompt.md` — human-readable device summary for raw system-prompt injection.

These flat files are intentionally skipped when ``--output-dir`` points elsewhere (e.g.
``~/.claude/skills``) so that agent skill loaders only see proper per-device skill dirs.

Devices are enriched with profile metadata (Tuya + miIO have profile registries) so each
device gets *its own* property list rather than a generic protocol-level fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from iotcli.config.manager import ConfigManager
from iotcli.core.device import Device
from iotcli.core.registry import protocol_registry
from iotcli.protocols.base import Property
from iotcli.skills.engine import render


def _build_openclaw_metadata(device: Device) -> str:
    """Return a compact JSON string with OpenClaw metadata for the skill frontmatter."""
    return json.dumps(
        {"openclaw": {"requires": {"bins": ["iotcli"]}, "os": ["darwin", "linux", "win32"]}},
        separators=(",", ":"),
    )


# Heuristic: infer a miIO profile from a device name when the user hasn't set one.
_MIIO_NAME_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("airfryer", "air-fryer", "fryer"), "airfryer"),
    (("camera", "cam"), "camera"),
    (("vacuum", "roborock", "robot"), "vacuum"),
    (("bulb", "led", "light", "lamp", "yeelight"), "bulb"),
]


def _infer_miio_profile(device: Device) -> str:
    if device.profile:
        return device.profile
    name = device.name.lower()
    for hints, profile in _MIIO_NAME_HINTS:
        if any(h in name for h in hints):
            return profile
    return "generic"


def build_device_context(device: Device) -> dict[str, Any]:
    """Build a per-device metadata dict enriched with profile-aware properties.

    This is the single source of truth for "what does this device look like to
    the outside world" — it powers both the skill generator (per-device SKILL.md
    + iotcli.tools.json) and the MCP server (per-device tool schemas). Keeping
    one builder means an agent calling iotcli over MCP and an agent reading the
    generated skill files see exactly the same property/range/enum data.

    Returns a dict with: device, meta, profile_name, capabilities, properties
    (list[Property]), status_properties (list[Property]), settable_names,
    trigger_names, actions (dict[str, str]).
    """
    cls = protocol_registry.get(device.protocol)
    meta = cls.meta if cls and hasattr(cls, "meta") else None

    capabilities = list(meta.capabilities) if meta else ["on", "off", "status", "set"]
    properties: list[Property] = []
    status_properties: list[Property] = []
    actions: dict[str, str] = {}
    profile_name: str | None = device.profile

    # Tuya / petfeeder profile enrichment
    if device.protocol in ("tuya", "petfeeder"):
        try:
            from iotcli.protocols.tuya import TUYA_PROFILES

            profile_name = device.profile or (
                "petfeeder" if device.protocol == "petfeeder" else "generic"
            )
            profile_cls = TUYA_PROFILES.get(profile_name)
            if profile_cls:
                profile = profile_cls()
                properties = list(profile.properties)
                status_properties = list(profile.status_properties)
                actions = dict(profile.actions)
        except Exception:
            pass

    # miIO profile enrichment
    elif device.protocol == "miio":
        try:
            from iotcli.protocols.miio import MIIO_PROFILES

            profile_name = _infer_miio_profile(device)
            profile_cls = MIIO_PROFILES.get(profile_name, MIIO_PROFILES["generic"])
            profile = profile_cls()
            properties = list(profile.properties)
            status_properties = list(profile.status_properties)
        except Exception:
            pass

    # Fall back to protocol-level rich properties (lgac, http, mqtt)
    if not properties and meta and meta.properties:
        properties = list(meta.properties)
    if not status_properties and meta and meta.status_properties:
        status_properties = list(meta.status_properties)

    # Last-resort fallback: synthesize bare Property stubs from settable_properties
    if not properties and meta:
        properties = [Property(name=p, type="str") for p in meta.settable_properties]
    if not status_properties:
        status_properties = [
            Property(name="online", type="bool", settable=False),
            Property(name="power", type="str", settable=False),
        ]

    # Filter out trigger props from "settable property names" (they're invoked
    # without a value via on/off or as bare actions).
    settable_names = [p.name for p in properties if p.settable and p.type != "trigger"]
    trigger_names = [p.name for p in properties if p.type == "trigger"]

    return {
        "device": device,
        "meta": meta,
        "profile_name": profile_name,
        "capabilities": capabilities,
        "properties": properties,
        "status_properties": status_properties,
        "settable_names": settable_names,
        "trigger_names": trigger_names,
        "actions": actions,
        "skill_name": device.name.replace("-", "_"),
        "metadata_json": _build_openclaw_metadata(device),
    }


# Per-profile one-liners appended to the frontmatter description.
# Keep these short — they appear in the agent's skill-selection context.
_PROFILE_DESCRIPTION_NOTES: dict[str, str] = {
    "petfeeder": " Use `set portions=N` to feed — `on` only triggers one quick portion.",
    "light": " Use `set brightness` / `set color_temp` for fine control, not just on/off.",
    "bulb": " Use `set brightness` / `set color_temp` for fine control, not just on/off.",
    "airfryer": " Requires both `temperature` and `timer` to start a cooking session.",
}

# Per-profile pitfall bullets shown in the ## Agent Guidance section.
_PROFILE_PITFALLS: dict[str, list[str]] = {
    "petfeeder": [
        "`on` triggers exactly **one quick portion** — it does NOT let you choose the amount.",
        "To dispense a specific amount use `set \"portions=N\"` (N = 1–10). This is the correct command for scheduled or on-demand feeding.",
        "To dispense a specific amount use `set \"portions=N\"` (N = 1–60). This is the correct command for scheduled or on-demand feeding.",
        "Always query status first to check `food_level` before feeding — dispense may fail silently if the hopper is empty.",
    ],
    "airfryer": [
        "Setting only `temperature` without `timer` (or vice-versa) will not start cooking.",
        "Check `status` after issuing a cook command — the appliance may reject the combination if the basket is not inserted.",
    ],
    "light": [
        "Sending `on` without setting `brightness` may restore the last brightness, which could be 0% — always set brightness explicitly after turning on.",
    ],
    "bulb": [
        "Sending `on` without setting `brightness` may restore the last brightness, which could be 0% — always set brightness explicitly after turning on.",
    ],
}


class SkillGenerator:
    """Generates AI agent skill files for configured devices."""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.skills_dir = config.config_dir / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    # -- public API -----------------------------------------------------------

    def generate_all(self, output_dir: str | None = None) -> list[str]:
        """Generate per-device SKILL.md dirs for all configured devices.

        When ``output_dir`` is omitted (or matches the canonical ``~/.iotcli/skills/``
        default), the admin files ``iotcli.tools.json``, ``iotcli.skill.yaml``, and
        ``system_prompt.md`` are also written. They are skipped for external output
        directories to avoid polluting agent skill loaders with non-skill files.

        Cleans stale per-device skill directories whose device no longer exists.
        """
        out = Path(output_dir) if output_dir else self.skills_dir
        out.mkdir(parents=True, exist_ok=True)

        devices = self.config.get_all_devices()
        results: list[str] = []

        # Per-device skill directories
        live_slugs: set[str] = set()
        for name, device in devices.items():
            path = self._write_device_skill(device, out)
            results.append(str(path))
            live_slugs.add(device.name)

        # Only purge legacy flat `*.skill.md` files when writing into the
        # canonical default skills_dir. A user-supplied custom output_dir is
        # treated as foreign territory — we still remove orphan per-device
        # SKILL.md dirs (we created those), but never touch unfamiliar files.
        is_default_dir = out.resolve() == self.skills_dir.resolve()
        self._cleanup_stale(out, live_slugs, purge_legacy=is_default_dir)

        # Flat admin files (tools.json, skill.yaml, system_prompt.md) are only
        # written into the canonical skills dir. When the user points --output
        # at an external location (e.g. ~/.claude/skills) we skip them so they
        # don't pollute the agent's skill loader with non-skill files.
        if is_default_dir:
            path = self._write_tools_json(devices, out)
            results.append(str(path))

            path = self._write_global_skill(devices, out)
            results.append(str(path))

            path = self._write_system_prompt(devices, out)
            results.append(str(path))

        return results

    def generate_device_skill(self, device: Device, output_dir: str | None = None) -> str:
        """Generate skill file for a single device."""
        out = Path(output_dir) if output_dir else self.skills_dir
        out.mkdir(parents=True, exist_ok=True)
        return str(self._write_device_skill(device, out))

    def list_skills(self) -> list[str]:
        """List generated skill artifacts (per-device dirs + top-level files)."""
        if not self.skills_dir.exists():
            return []
        items: list[str] = []
        for p in sorted(self.skills_dir.iterdir()):
            if p.is_dir() and (p / "SKILL.md").exists():
                items.append(f"{p.name}/SKILL.md")
            elif p.is_file():
                items.append(p.name)
        return items

    def get_skill_content(self, device_name: str) -> str | None:
        """Read a device skill file, or None if not found.

        Looks first at the new ``<slug>/SKILL.md`` layout, then falls back to the
        legacy flat ``<slug>.skill.md`` for back-compat.
        """
        new_path = self.skills_dir / device_name / "SKILL.md"
        if new_path.exists():
            return new_path.read_text()
        legacy = self.skills_dir / f"{device_name}.skill.md"
        if legacy.exists():
            return legacy.read_text()
        return None

    # -- internal -------------------------------------------------------------

    def _device_context(self, device: Device) -> dict[str, Any]:
        """Build template context for a device, enriched with profile metadata."""
        ctx = build_device_context(device)
        ctx["description"] = self._build_description(
            device, ctx["profile_name"], ctx["meta"], ctx["properties"],
            ctx["trigger_names"], ctx["actions"],
        )
        ctx["pitfalls"] = self._build_pitfalls(ctx["profile_name"], ctx["properties"])
        return ctx

    def _build_description(
        self,
        device: Device,
        profile_name: str | None,
        meta: Any,
        properties: list,
        trigger_names: list[str],
        actions: dict[str, str],
    ) -> str:
        """Build a concise, action-oriented description for the skill frontmatter.

        The description is the primary signal agents use to decide whether to invoke
        this skill — it should name concrete actions and key property ranges, not just
        say "control the device".
        """
        proto = meta.display_name if meta else device.protocol
        location = f"at {device.ip}" if device.ip and device.ip != "0.0.0.0" else "(cloud)"

        # Build a compact list of what the agent can actually do.
        action_parts: list[str] = []

        settable = [p for p in properties if p.settable and p.type != "trigger"]
        for p in settable[:4]:
            if p.enum:
                vals = "/".join(str(v) for v in p.enum[:4])
                if len(p.enum) > 4:
                    vals += "/…"
                action_parts.append(f"set {p.name} ({vals})")
            elif p.minimum is not None and p.maximum is not None:
                unit = f" {p.unit}" if p.unit else ""
                action_parts.append(f"set {p.name} ({p.minimum}–{p.maximum}{unit})")
            else:
                action_parts.append(f"set {p.name}")

        for name in trigger_names[:2]:
            action_parts.append(f"trigger {name}")

        for name in list(actions.keys())[:2]:
            action_parts.append(name)

        if not action_parts:
            action_parts = ["turn on/off", "query status"]

        action_str = "; ".join(action_parts)

        # Profile-specific clarification to prevent common agent mistakes.
        note = _PROFILE_DESCRIPTION_NOTES.get(profile_name or "", "")

        return f"{proto} '{device.name}' {location} — {action_str}.{note}"

    @staticmethod
    def _build_pitfalls(profile_name: str | None, properties: list) -> list[str]:
        """Return a list of agent-facing pitfall warnings for this device profile."""
        return list(_PROFILE_PITFALLS.get(profile_name or "", []))

    def _write_device_skill(self, device: Device, out_dir: Path) -> Path:
        ctx = self._device_context(device)
        content = render("device_skill.md.j2", **ctx)
        device_dir = out_dir / device.name
        device_dir.mkdir(parents=True, exist_ok=True)
        path = device_dir / "SKILL.md"
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
                "profile": ctx["profile_name"],
                "capabilities": ctx["capabilities"],
                "settable_properties": ctx["settable_names"],
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
                "profile": ctx["profile_name"],
                "properties": ctx["properties"],
                "actions": ctx["actions"],
            })
        content = render("system_prompt.md.j2", devices=device_contexts)
        path = out_dir / "system_prompt.md"
        path.write_text(content)
        return path

    def _write_tools_json(self, devices: dict[str, Device], out_dir: Path) -> Path:
        """Emit an OpenAI/Anthropic-compatible tool schema for the iotcli CLI.

        Each device contributes its own per-device parameter schema (with enums,
        ranges, types) under the `devices` map. Generic CLI commands are exposed
        as top-level tools so an agent can call them through structured tool use.
        """
        device_specs: dict[str, Any] = {}
        for name, dev in devices.items():
            ctx = self._device_context(dev)
            props = ctx["properties"]
            settable_props = {
                p.name: p.to_jsonschema()
                for p in props
                if p.settable and p.type != "trigger"
            }
            triggers = [p.name for p in props if p.type == "trigger"]
            status_props = {p.name: p.to_jsonschema() for p in ctx["status_properties"]}

            device_specs[dev.name] = {
                "protocol": dev.protocol,
                "profile": ctx["profile_name"],
                "ip": dev.ip,
                "settable_properties": settable_props,
                "triggers": triggers,
                "status_fields": status_props,
                "actions": ctx["actions"],
            }

        # Shared `device` parameter schema — kept consistent across every tool
        # so an agent always sees the same description and enum.
        device_param: dict[str, Any] = {
            "type": "string",
            "description": "Device slug as shown in `iotcli --json list`.",
            "enum": sorted(devices.keys()),
        }

        # Top-level tool definitions in OpenAI function-calling shape.
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "iotcli_list",
                    "description": "List all configured iotcli devices with their protocols, IPs, and configured status.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "iotcli_status",
                    "description": "Query the live status of a single device.",
                    "parameters": {
                        "type": "object",
                        "properties": {"device": dict(device_param)},
                        "required": ["device"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "iotcli_status_all",
                    "description": "Query the live status of all configured devices in parallel.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "iotcli_turn_on",
                    "description": "Turn a device on. For pet feeders this triggers a quick feed.",
                    "parameters": {
                        "type": "object",
                        "properties": {"device": dict(device_param)},
                        "required": ["device"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "iotcli_turn_off",
                    "description": "Turn a device off. No-op for pet feeders.",
                    "parameters": {
                        "type": "object",
                        "properties": {"device": dict(device_param)},
                        "required": ["device"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "iotcli_set",
                    "description": (
                        "Set a property on a device. Allowed properties and value ranges "
                        "depend on the device — see the per-device schema in `devices` "
                        "below for the exact `property` enum and `value` constraints."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device": dict(device_param),
                            "property": {"type": "string"},
                            "value": {
                                "description": "Value for the property. Type and constraints vary per (device, property) pair."
                            },
                        },
                        "required": ["device", "property", "value"],
                    },
                },
            },
        ]

        spec = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "name": "iotcli",
            "version": 2,
            "description": (
                "Universal IoT device control CLI. Each tool maps to an `iotcli --json` "
                "subcommand. Use the `devices` map to look up the legal `property` and "
                "`value` arguments for each device before calling `iotcli_set`."
            ),
            "cli_invocation": {
                "iotcli_list": "iotcli --json list",
                "iotcli_status": "iotcli --json control status \"<device>\"",
                "iotcli_status_all": "iotcli --json status-all",
                "iotcli_turn_on": "iotcli --json control on \"<device>\"",
                "iotcli_turn_off": "iotcli --json control off \"<device>\"",
                "iotcli_set": "iotcli --json control set \"<device>\" \"<property>=<value>\"",
            },
            "tools": tools,
            "devices": device_specs,
        }

        path = out_dir / "iotcli.tools.json"
        path.write_text(json.dumps(spec, indent=2))
        return path

    def _cleanup_stale(
        self, out_dir: Path, live_slugs: set[str], *, purge_legacy: bool = True
    ) -> None:
        """Remove orphan per-device skill dirs and (optionally) legacy
        `*.skill.md` files.

        ``purge_legacy`` should be False when writing into a user-supplied
        custom directory — otherwise we'd silently delete files we did not
        create.
        """
        if not out_dir.exists():
            return
        # Remove stale directories — these are always ones we created.
        for child in out_dir.iterdir():
            if child.is_dir() and (child / "SKILL.md").exists():
                if child.name not in live_slugs:
                    try:
                        (child / "SKILL.md").unlink()
                        # Remove dir if empty
                        if not any(child.iterdir()):
                            child.rmdir()
                    except OSError:
                        pass
            # Legacy flat `<slug>.skill.md` files from earlier iotcli releases.
            # Only purge them when writing into the canonical default skills
            # directory; a custom output_dir may contain unrelated user files
            # that happen to share the suffix.
            elif (
                purge_legacy
                and child.is_file()
                and child.name.endswith(".skill.md")
            ):
                try:
                    child.unlink()
                except OSError:
                    pass
