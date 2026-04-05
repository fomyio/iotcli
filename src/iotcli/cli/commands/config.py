"""iotcli config — show / reset configuration."""

from __future__ import annotations

import click

from iotcli.cli.output import Output
from iotcli.config.manager import ConfigManager
from iotcli.tui.panels import config_summary


@click.command("config-show")
@click.pass_context
def config_show(ctx):
    """Display current configuration."""
    out = Output(ctx.obj["json_output"])
    cfg: ConfigManager = ctx.obj["config"]

    devices = cfg.get_all_devices()
    if not devices:
        out.echo("No devices configured.")
        return

    if out.json_mode:
        out.json_out({
            "config_dir": str(cfg.config_dir),
            "devices": {
                n: d.to_config() for n, d in devices.items()
            },
        })
        return

    config_summary(devices)
