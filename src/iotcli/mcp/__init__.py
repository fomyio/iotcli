"""MCP (Model Context Protocol) integration — exposes iotcli to AI agents.

Lets Claude Desktop, Cursor, Zed, and other MCP-compatible clients control
configured IoT devices directly through structured tool calls and resources.

The MCP server reuses ConfigManager + DeviceController in-process — no shell
out, no marshalling layer. Per-device JSON Schema for tool inputs is generated
from the same ``Property`` definitions the skill generator uses, so there is
exactly one source of truth.

Importing this module does not pull in the optional ``mcp`` SDK; that happens
inside :mod:`iotcli.mcp.server` so users without the extras installed can still
import the rest of iotcli.
"""
