"""MCP resource definitions — exposes device info and tool schemas as readable resources.

Resources let an agent inspect device metadata (settable properties, value
constraints, protocol details) before calling a tool. This is the MCP
equivalent of reading ``iotcli.tools.json`` — but live, so it always reflects
the current config.
"""

from __future__ import annotations

import json
from typing import Any

import mcp.types as types

from iotcli.config.manager import ConfigManager
from iotcli.skills.generator import build_device_context


RESOURCE_PREFIX = "iotcli://"


def list_resources(cfg: ConfigManager) -> list[types.Resource]:
    """Return all available resources."""
    resources = [
        types.Resource(
            uri=f"{RESOURCE_PREFIX}devices",
            name="All devices",
            description="List of all configured iotcli devices with protocol, IP, and status.",
            mimeType="application/json",
        ),
        types.Resource(
            uri=f"{RESOURCE_PREFIX}schema",
            name="Tool schema",
            description="Full iotcli tool schema with per-device property definitions.",
            mimeType="application/json",
        ),
    ]

    for name in sorted(cfg.device_names()):
        resources.append(types.Resource(
            uri=f"{RESOURCE_PREFIX}device/{name}",
            name=name,
            description=f"Detailed schema for device '{name}' — settable properties, ranges, enums.",
            mimeType="application/json",
        ))

    return resources


def read_resource(uri: str, cfg: ConfigManager) -> str:
    """Read a single resource by URI. Returns JSON string."""

    if uri == f"{RESOURCE_PREFIX}devices":
        devices = cfg.get_all_devices()
        return json.dumps({
            "devices": [
                {
                    "name": n,
                    "protocol": d.protocol,
                    "ip": d.ip,
                    "port": d.port,
                    "status": d.status.value,
                    "profile": d.profile,
                }
                for n, d in devices.items()
            ]
        }, indent=2)

    if uri == f"{RESOURCE_PREFIX}schema":
        return _build_schema(cfg)

    if uri.startswith(f"{RESOURCE_PREFIX}device/"):
        device_name = uri[len(f"{RESOURCE_PREFIX}device/"):]
        return _device_detail(cfg, device_name)

    return json.dumps({"error": f"Unknown resource: {uri}"})


def _device_detail(cfg: ConfigManager, name: str) -> str:
    device = cfg.get_device_or_none(name)
    if not device:
        return json.dumps({"error": f"Device not found: {name}"})

    ctx = build_device_context(device)
    settable = {
        p.name: p.to_jsonschema()
        for p in ctx["properties"]
        if p.settable and p.type != "trigger"
    }
    triggers = [p.name for p in ctx["properties"] if p.type == "trigger"]
    status_fields = {p.name: p.to_jsonschema() for p in ctx["status_properties"]}

    return json.dumps({
        "name": device.name,
        "protocol": device.protocol,
        "ip": device.ip,
        "port": device.port,
        "profile": ctx["profile_name"],
        "capabilities": ctx["capabilities"],
        "settable_properties": settable,
        "triggers": triggers,
        "status_fields": status_fields,
        "actions": ctx["actions"],
    }, indent=2)


def _build_schema(cfg: ConfigManager) -> str:
    """Build the same schema structure as iotcli.tools.json but live."""
    devices = cfg.get_all_devices()
    device_specs: dict[str, Any] = {}

    for name, dev in devices.items():
        ctx = build_device_context(dev)
        settable = {
            p.name: p.to_jsonschema()
            for p in ctx["properties"]
            if p.settable and p.type != "trigger"
        }
        triggers = [p.name for p in ctx["properties"] if p.type == "trigger"]
        status_fields = {p.name: p.to_jsonschema() for p in ctx["status_properties"]}

        device_specs[name] = {
            "protocol": dev.protocol,
            "profile": ctx["profile_name"],
            "ip": dev.ip,
            "settable_properties": settable,
            "triggers": triggers,
            "status_fields": status_fields,
            "actions": ctx["actions"],
        }

    return json.dumps({
        "name": "iotcli",
        "description": "Live device schema — settable properties, ranges, and enums per device.",
        "devices": device_specs,
    }, indent=2)
