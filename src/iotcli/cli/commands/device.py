"""iotcli add / remove / list / status-all — device management commands."""

from __future__ import annotations

import sys
from typing import Any

import click

from iotcli.cli.output import Output
from iotcli.config.manager import ConfigManager
from iotcli.core.controller import DeviceController
from iotcli.core.device import DeviceStatus
from iotcli.core.registry import protocol_registry


# ── add (non-interactive, for AI agents / scripting) ────────────────────────


@click.command()
@click.option("--name", "-n", required=True, help="Device name (unique)")
@click.option("--protocol", "-p", required=True, help="Device protocol")
@click.option("--ip", required=True, help="Device IP address")
@click.option("--port", type=int, default=None, help="Port (uses protocol default)")
@click.option("--token", default=None, help="miIO 32-char hex token")
@click.option("--device-id", "device_id", default=None, help="Device ID")
@click.option("--local-key", "local_key", default=None, help="Tuya local key")
@click.option("--version", "tuya_version", default="3.3", help="Tuya protocol version")
@click.option("--profile", default=None, help="Tuya device profile (petfeeder, light, switch)")
@click.option("--pat-token", "pat_token", default=None, help="LG ThinQ PAT")
@click.option("--country", default=None, help="Country code for LG AC")
@click.option("--username", default=None, help="MQTT username")
@click.option("--password", default=None, help="MQTT password")
@click.option("--device-type", "device_type", default="generic", help="HTTP device type")
@click.option("--topic-prefix", "topic_prefix", default=None, help="MQTT topic prefix")
@click.option("--no-test", is_flag=True, help="Skip connection test")
@click.pass_context
def add(ctx, name, protocol, ip, port, token, device_id, local_key, tuya_version,
        profile, pat_token, country, username, password, device_type, topic_prefix, no_test):
    """Add a device non-interactively (for AI agents / scripting)."""
    out = Output(ctx.obj["json_output"])
    cfg: ConfigManager = ctx.obj["config"]

    # Validate protocol exists
    if protocol not in protocol_registry:
        out.error(f"Unknown protocol: {protocol}. Available: {', '.join(protocol_registry.names())}")

    cls = protocol_registry.get_or_raise(protocol)
    meta = cls.meta

    # Validate required credentials
    errors = []
    if "token" in meta.required_credentials and not token:
        errors.append("--token is required")
    if "device_id" in meta.required_credentials and not device_id:
        errors.append("--device-id is required")
    if "local_key" in meta.required_credentials and not local_key:
        errors.append("--local-key is required")
    if "pat_token" in meta.required_credentials and not pat_token:
        errors.append("--pat-token is required")
    if errors:
        out.error("; ".join(errors))

    device_dict: dict[str, Any] = {
        "name": name,
        "protocol": protocol,
        "ip": ip,
        "port": port or meta.default_port,
        "status": "configured",
    }
    if token:
        device_dict["token"] = token
    if device_id:
        device_dict["device_id"] = device_id
    if local_key:
        device_dict["local_key"] = local_key
    if pat_token:
        device_dict["pat_token"] = pat_token
    if country:
        device_dict["country"] = country.upper()
    if username:
        device_dict["username"] = username
    if password:
        device_dict["password"] = password
    if protocol in ("tuya", "petfeeder"):
        device_dict["version"] = tuya_version
    if profile:
        device_dict["profile"] = profile
    elif protocol == "petfeeder":
        device_dict["profile"] = "petfeeder"
    if protocol == "http":
        device_dict["device_type"] = device_type
    if topic_prefix:
        device_dict["topic_prefix"] = topic_prefix

    if not no_test:
        out.echo(f"Testing connection to {name}...")
        try:
            from iotcli.core.device import Device
            from iotcli.config.credentials import SENSITIVE_FIELDS
            creds = {k: device_dict[k] for k in SENSITIVE_FIELDS if device_dict.get(k)}
            dev = Device.from_config(device_dict, credentials=creds)
            ctrl = DeviceController(verbose=ctx.obj["verbose"], debug=ctx.obj["debug"])
            if not ctrl.test_connection(dev):
                out.error("Connection test failed — device NOT saved. Use --no-test to skip.")
        except Exception as e:
            out.error(f"Connection test error: {e}. Use --no-test to skip.")

    cfg.add_device(device_dict)
    from iotcli.core.device import slugify
    out.success(f"Device '{slugify(name)}' saved.", {"device": slugify(name)})


# ── remove ──────────────────────────────────────────────────────────────────


@click.command()
@click.argument("device_name")
@click.pass_context
def remove(ctx, device_name):
    """Remove a device from configuration."""
    out = Output(ctx.obj["json_output"])
    cfg: ConfigManager = ctx.obj["config"]

    if cfg.remove_device(device_name):
        out.success(f"Removed: {device_name}", {"device": device_name})
    else:
        out.error(f"Device not found: {device_name}")


# ── list ────────────────────────────────────────────────────────────────────


@click.command("list")
@click.option("--protocol", "-p", help="Filter by protocol")
@click.option("--status", "-s", help="Filter by status")
@click.pass_context
def list_devices(ctx, protocol, status):
    """List all configured devices."""
    out = Output(ctx.obj["json_output"])
    cfg: ConfigManager = ctx.obj["config"]

    devices = cfg.get_all_devices()
    if not devices:
        out.success("No devices configured.", {"devices": []})
        return

    filtered = {
        n: d for n, d in devices.items()
        if (not protocol or d.protocol == protocol)
        and (not status or d.status.value == status)
    }

    if out.json_mode:
        out.json_out({
            "devices": [
                {
                    "name": n,
                    "protocol": d.protocol,
                    "ip": d.ip,
                    "port": d.port,
                    "status": d.status.value,
                    "profile": d.profile,
                    "has_credentials": bool(d.credentials),
                }
                for n, d in filtered.items()
            ]
        })
        return

    if not filtered:
        out.echo("No devices match the filter.")
        return

    from iotcli.tui.panels import config_summary
    config_summary(filtered)


# ── status-all ──────────────────────────────────────────────────────────────


@click.command("status-all")
@click.pass_context
def status_all(ctx):
    """Get status of all configured devices in parallel."""
    out = Output(ctx.obj["json_output"])
    cfg: ConfigManager = ctx.obj["config"]
    ctrl = DeviceController(verbose=ctx.obj["verbose"], debug=ctx.obj["debug"])

    devices = cfg.get_all_devices()
    if not devices:
        out.success("No devices configured.", {"devices": {}})
        return

    if not out.json_mode:
        from rich.console import Console
        console = Console()
        with console.status("[bold blue]Querying all devices...", spinner="dots"):
            results = ctrl.status_all(devices)
    else:
        results = ctrl.status_all(devices)

    for name, status in results.items():
        if status.get("online"):
            cfg.update_status(name, DeviceStatus.ONLINE)
        else:
            cfg.update_status(name, DeviceStatus.OFFLINE)

    if out.json_mode:
        out.json_out({"devices": results})
    else:
        from iotcli.tui.prompts import status_panel
        for name, status in results.items():
            status_panel(name, status)
