"""iotcli control — on/off/status/set for individual devices."""

from __future__ import annotations

import sys

import click

from iotcli.cli.output import Output
from iotcli.config.manager import ConfigManager
from iotcli.core.controller import DeviceController
from iotcli.core.device import DeviceStatus


def _coerce(raw: str):
    """Type-coerce a string value from the CLI."""
    low = raw.lower()
    if low in ("true", "on", "yes"):
        return True
    if low in ("false", "off", "no"):
        return False
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw


@click.command()
@click.argument("action", type=click.Choice(["on", "off", "status", "set"]))
@click.argument("device_name")
@click.argument("value", required=False)
@click.pass_context
def control(ctx, action, device_name, value):
    """Control a device: on, off, status, set property=value."""
    out = Output(ctx.obj["json_output"])
    cfg: ConfigManager = ctx.obj["config"]

    device = cfg.get_device_or_none(device_name)
    device = cfg.get_device_or_none(device_name)
    if not device:
        out.error(f"Device not found: {device_name}")
        return
    ctrl = DeviceController(verbose=ctx.obj["verbose"], debug=ctx.obj["debug"])

    try:
        if action == "on":
            if not out.json_mode:
                from rich.console import Console
                console = Console()
                with console.status(f"[bold blue]Turning on {device_name}...", spinner="dots"):
                    ok = ctrl.turn_on(device)
            else:
                ok = ctrl.turn_on(device)
            if ok:
                cfg.update_status(device_name, DeviceStatus.ONLINE)
                out.success(f"{device_name} is now ON", {"device": device_name, "action": "on"})
            else:
                out.error(f"Failed to turn on {device_name}")

        elif action == "off":
            if not out.json_mode:
                from rich.console import Console
                console = Console()
                with console.status(f"[bold blue]Turning off {device_name}...", spinner="dots"):
                    ok = ctrl.turn_off(device)
            else:
                ok = ctrl.turn_off(device)
            if ok:
                cfg.update_status(device_name, DeviceStatus.ONLINE)
                out.success(f"{device_name} is now OFF", {"device": device_name, "action": "off"})
            else:
                out.error(f"Failed to turn off {device_name}")

        elif action == "status":
            if not out.json_mode:
                from rich.console import Console
                console = Console()
                with console.status(f"[bold blue]Querying {device_name}...", spinner="dots"):
                    status = ctrl.get_status(device)
            else:
                status = ctrl.get_status(device)
            if status.get("online"):
                cfg.update_status(device_name, DeviceStatus.ONLINE)
            else:
                cfg.update_status(device_name, DeviceStatus.OFFLINE)
            if out.json_mode:
                out.device_status(device_name, status)
            else:
                from iotcli.tui.prompts import status_panel
                status_panel(device_name, status)

        elif action == "set":
            if not value or "=" not in value:
                out.error("'set' requires value in format: property=value")
            prop, raw = value.split("=", 1)
            coerced = _coerce(raw)
            out.echo(f"Setting {device_name}.{prop} = {coerced}...")
            ok = ctrl.set_value(device, prop, coerced)
            if ok:
                cfg.update_status(device_name, DeviceStatus.ONLINE)
                out.success(f"Set {prop} = {coerced}", {"property": prop, "value": coerced})
            else:
                out.error(f"Failed to set {prop}")

    except Exception as e:
        out.error(str(e))
