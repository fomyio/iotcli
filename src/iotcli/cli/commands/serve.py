"""iotcli serve — launch protocol servers (MCP, etc.)."""

from __future__ import annotations

import click


@click.group()
def serve():
    """Start a server that exposes iotcli to external clients."""


@serve.command("mcp")
@click.pass_context
def serve_mcp(ctx):
    """Start an MCP (Model Context Protocol) server on stdio.

    Connect Claude Desktop, Cursor, or any MCP-compatible client to control
    your IoT devices through structured tool calls.

    Example Claude Desktop config (claude_desktop_config.json):

    \b
        {
          "mcpServers": {
            "iotcli": {
              "command": "iotcli",
              "args": ["serve", "mcp"]
            }
          }
        }
    """
    try:
        from iotcli.mcp.server import main as mcp_main
    except ImportError:
        click.echo(
            "Error: MCP dependencies not installed.\n"
            "Install them with: pip install iotcli[mcp]",
            err=True,
        )
        raise SystemExit(1)

    cfg = ctx.obj["config"]
    mcp_main(cfg)
