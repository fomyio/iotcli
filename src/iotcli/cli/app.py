"""Main CLI application — Click entry point."""

from __future__ import annotations

import json

import click

from iotcli import __version__
from iotcli.config.manager import ConfigManager

# Import protocols to trigger auto-registration
import iotcli.protocols  # noqa: F401

from iotcli.cli.commands.discover import discover
from iotcli.cli.commands.control import control
from iotcli.cli.commands.device import add, remove, list_devices, status_all
from iotcli.cli.commands.config import config_show
from iotcli.cli.commands.skills import skills
from iotcli.cli.commands.serve import serve


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="iotcli")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--debug", "-d", is_flag=True, help="Debug mode")
@click.option("--json", "json_output", is_flag=True, help="JSON output (for AI agents)")
@click.pass_context
def cli(ctx, verbose, debug, json_output):
    """
    iotcli — Universal IoT device control CLI.

    Control Xiaomi miIO, Tuya, MQTT, HTTP (ESPHome/Tasmota), and LG AC
    devices on your local network. Works for humans and AI agents alike.

    Use --json for machine-readable output.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["debug"] = debug
    ctx.obj["json_output"] = json_output
    ctx.obj["config"] = ConfigManager()

    # Only act when no subcommand was given (bare `iotcli`)
    if ctx.invoked_subcommand is not None:
        return

    if json_output:
        # Machine-readable command list for AI agents
        commands = sorted(cli.list_commands(ctx))
        click.echo(json.dumps({
            "version": __version__,
            "commands": commands,
        }, indent=2))
        return

    # Interactive welcome screen — loops until user picks Exit or Ctrl+C
    from iotcli.tui.welcome import run_interactive
    run_interactive(ctx)


# Register commands
cli.add_command(discover)
cli.add_command(add)
cli.add_command(remove)
cli.add_command(list_devices)
cli.add_command(status_all)
cli.add_command(control)
cli.add_command(config_show)
cli.add_command(skills)
cli.add_command(serve)


# Interactive wizard — separate because it needs TUI
@cli.command()
@click.pass_context
def setup(ctx):
    """Interactive device setup wizard (TUI)."""
    from iotcli.tui.wizard import SetupWizard

    wizard = SetupWizard(
        config=ctx.obj["config"],
        verbose=ctx.obj["verbose"],
        debug=ctx.obj["debug"],
    )
    wizard.run()


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
