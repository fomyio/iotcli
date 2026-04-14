"""MCP server — stdio transport for Claude Desktop / Cursor / Zed integration.

Usage:
    iotcli serve mcp          # stdio (default — what Claude Desktop expects)

The server exposes every configured device as tools (list, status, on, off, set)
and resources (device schemas, tool spec). All operations run in-process via
ConfigManager + DeviceController — no shell-out.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from iotcli.config.manager import ConfigManager
from iotcli.core.controller import DeviceController

# Protocol imports trigger auto-registration
import iotcli.protocols  # noqa: F401

from iotcli.mcp.tools import list_tools, handle_tool
from iotcli.mcp.resources import list_resources, read_resource

logger = logging.getLogger(__name__)


def create_server(cfg: ConfigManager | None = None) -> Server:
    """Build a configured MCP Server instance.

    Parameters
    ----------
    cfg : ConfigManager, optional
        Injected config — defaults to the standard ``~/.iotcli`` dir. Passing
        an explicit manager is useful for testing.
    """
    if cfg is None:
        cfg = ConfigManager()

    ctrl = DeviceController()
    server = Server("iotcli")

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return list_tools(cfg)

    @server.call_tool()
    async def _call_tool(
        name: str, arguments: dict[str, Any]
    ) -> list[types.TextContent]:
        return await handle_tool(name, arguments or {}, cfg, ctrl)

    @server.list_resources()
    async def _list_resources() -> list[types.Resource]:
        return list_resources(cfg)

    @server.read_resource()
    async def _read_resource(uri: types.AnyUrl) -> str:
        return read_resource(str(uri), cfg)

    return server


async def run_stdio(cfg: ConfigManager | None = None) -> None:
    """Launch the MCP server on stdin/stdout."""
    server = create_server(cfg)
    init_options = server.create_initialization_options()
    logger.info("iotcli MCP server starting (stdio)")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_options)


def main(cfg: ConfigManager | None = None) -> None:
    """Synchronous entry point — called by the CLI command."""
    asyncio.run(run_stdio(cfg))
