"""iotcli discover — network device discovery."""

from __future__ import annotations

import click

from iotcli.cli.output import Output
from iotcli.discovery.scanner import DiscoveryScanner, ScanConfig


@click.command()
@click.option("--network", "-n", help="Network CIDR (e.g. 192.168.1.0/24)")
@click.option("--timeout", "-t", default=5, type=int, help="Scan timeout in seconds")
@click.pass_context
def discover(ctx, network, timeout):
    """Scan the local network for IoT devices."""
    out = Output(ctx.obj["json_output"])

    out.echo("Scanning for devices...")

    scanner = DiscoveryScanner(
        verbose=ctx.obj["verbose"],
        debug=ctx.obj["debug"],
        config=ScanConfig(timeout=timeout),
    )
    devices = scanner.discover_sync(network=network, timeout=timeout)

    if out.json_mode:
        out.json_out({"devices": devices})
        return

    if not devices:
        out.echo("No IoT devices found.")
        out.echo("\nTips:")
        out.echo("  - Ensure devices are powered on and on the same network")
        out.echo("  - Try: iotcli discover --network 192.168.1.0/24")
        return

    out.echo(f"\nFound {len(devices)} device(s):\n")
    for dev in devices:
        out.echo(f"  {dev['name']}")
        out.echo(f"    protocol : {dev['protocol']}")
        out.echo(f"    ip       : {dev['ip']}")
        out.echo(f"    status   : {dev['status']}")
        if dev.get("missing_info"):
            out.echo(f"    missing  : {', '.join(dev['missing_info'])}")
        out.echo("")
