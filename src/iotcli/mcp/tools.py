"""MCP tool definitions and handlers.

Each tool maps 1-to-1 to an iotcli operation (list, status, on, off, set).
Input schemas are built from the same ``Property`` definitions that the skill
generator uses, so agents always get identical enum/range/type data regardless
of whether they read the static ``iotcli.tools.json`` or call the live MCP
server.
"""

from __future__ import annotations

import json
from typing import Any

import mcp.types as types

from iotcli.config.manager import ConfigManager
from iotcli.core.controller import DeviceController
from iotcli.core.device import Device
from iotcli.skills.generator import build_device_context


def _device_enum(cfg: ConfigManager) -> list[str]:
    return sorted(cfg.device_names())


def list_tools(cfg: ConfigManager) -> list[types.Tool]:
    """Return the set of MCP tools, with per-device enums baked in."""
    device_names = _device_enum(cfg)

    device_param = {
        "type": "string",
        "description": "Device slug as shown in iotcli list.",
    }
    if device_names:
        device_param["enum"] = device_names

    # Build per-device settable property info for the set tool description
    set_desc_parts = [
        "Set a property on a device. The allowed (property, value) pairs "
        "depend on the device — read the iotcli://device/<name> resource for "
        "the full schema before calling."
    ]

    # Build per-device property enums for the property parameter
    all_settable: set[str] = set()
    all_triggers: set[str] = set()
    for name in device_names:
        dev = cfg.get_device_or_none(name)
        if not dev:
            continue
        ctx = build_device_context(dev)
        all_settable.update(ctx["settable_names"])
        all_triggers.update(ctx["trigger_names"])

    property_param: dict[str, Any] = {
        "type": "string",
        "description": "Property name to set.",
    }
    all_props = sorted(all_settable | all_triggers)
    if all_props:
        property_param["enum"] = all_props

    return [
        types.Tool(
            name="iotcli_list_devices",
            description=(
                "List all configured iotcli devices with their protocols, "
                "IPs, and status."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="iotcli_get_status",
            description="Query the live status of a single device.",
            inputSchema={
                "type": "object",
                "properties": {"device": device_param},
                "required": ["device"],
            },
        ),
        types.Tool(
            name="iotcli_status_all",
            description="Query the live status of all configured devices in parallel.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="iotcli_turn_on",
            description=(
                "Turn a device on. For pet feeders this triggers a quick feed."
            ),
            inputSchema={
                "type": "object",
                "properties": {"device": device_param},
                "required": ["device"],
            },
        ),
        types.Tool(
            name="iotcli_turn_off",
            description="Turn a device off. No-op for pet feeders.",
            inputSchema={
                "type": "object",
                "properties": {"device": device_param},
                "required": ["device"],
            },
        ),
        types.Tool(
            name="iotcli_set_property",
            description="\n".join(set_desc_parts),
            inputSchema={
                "type": "object",
                "properties": {
                    "device": device_param,
                    "property": property_param,
                    "value": {
                        "description": (
                            "Value for the property. Type and constraints "
                            "vary per (device, property) pair."
                        ),
                    },
                },
                "required": ["device", "property", "value"],
            },
        ),
    ]


def _ok_response(data: Any) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


def _err_response(msg: str) -> list[types.TextContent]:
    return [types.TextContent(
        type="text",
        text=json.dumps({"success": False, "error": msg}, indent=2),
    )]


def _resolve_device(cfg: ConfigManager, args: dict) -> Device | None:
    name = args.get("device", "")
    if not name:
        return None
    return cfg.get_device_or_none(name)


async def handle_tool(
    name: str,
    arguments: dict[str, Any],
    cfg: ConfigManager,
    ctrl: DeviceController,
) -> list[types.TextContent]:
    """Dispatch a tool call and return MCP content blocks."""

    if name == "iotcli_list_devices":
        devices = cfg.get_all_devices()
        listing = [
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
        return _ok_response({"devices": listing})

    if name == "iotcli_get_status":
        device = _resolve_device(cfg, arguments)
        if not device:
            return _err_response(f"Device not found: {arguments.get('device')}")
        try:
            status = ctrl.get_status(device)
            return _ok_response({"device": device.name, **status})
        except Exception as e:
            return _err_response(str(e))

    if name == "iotcli_status_all":
        devices = cfg.get_all_devices()
        results = ctrl.status_all(devices)
        return _ok_response({"devices": results})

    if name == "iotcli_turn_on":
        device = _resolve_device(cfg, arguments)
        if not device:
            return _err_response(f"Device not found: {arguments.get('device')}")
        try:
            ok = ctrl.turn_on(device)
            if ok:
                return _ok_response({"success": True, "device": device.name, "action": "on"})
            return _err_response(f"Failed to turn on {device.name}")
        except Exception as e:
            return _err_response(str(e))

    if name == "iotcli_turn_off":
        device = _resolve_device(cfg, arguments)
        if not device:
            return _err_response(f"Device not found: {arguments.get('device')}")
        try:
            ok = ctrl.turn_off(device)
            if ok:
                return _ok_response({"success": True, "device": device.name, "action": "off"})
            return _err_response(f"Failed to turn off {device.name}")
        except Exception as e:
            return _err_response(str(e))

    if name == "iotcli_set_property":
        device = _resolve_device(cfg, arguments)
        if not device:
            return _err_response(f"Device not found: {arguments.get('device')}")
        prop = arguments.get("property", "")
        value = arguments.get("value")
        if not prop:
            return _err_response("Missing 'property' argument")
        try:
            ok = ctrl.set_value(device, prop, value)
            if ok:
                return _ok_response({
                    "success": True,
                    "device": device.name,
                    "property": prop,
                    "value": value,
                })
            return _err_response(f"Failed to set {prop} on {device.name}")
        except Exception as e:
            return _err_response(str(e))

    return _err_response(f"Unknown tool: {name}")
