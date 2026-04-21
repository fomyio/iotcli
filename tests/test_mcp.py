"""Tests for the MCP server — tools, resources, and server wiring.

Uses a temporary config dir with two fake devices so tests don't touch the
user's real ``~/.iotcli``. Device connectivity is not tested here (that would
require real hardware); instead we verify tool/resource schema correctness and
error handling for unknown devices.
"""

from __future__ import annotations

import json
import pytest

pytest.importorskip("mcp")

from iotcli.config.manager import ConfigManager
from iotcli.core.device import Device, DeviceStatus
from iotcli.mcp.tools import list_tools, handle_tool
from iotcli.mcp.resources import list_resources, read_resource
from iotcli.mcp.server import create_server
from iotcli.core.controller import DeviceController


@pytest.fixture
def cfg(tmp_path):
    """ConfigManager backed by a temp directory with two test devices."""
    config = ConfigManager(config_dir=tmp_path)
    config.add_device(Device(
        name="test-light",
        protocol="http",
        ip="192.168.1.10",
        port=80,
        status=DeviceStatus.CONFIGURED,
        device_type="tasmota",
    ))
    config.add_device(Device(
        name="test-ac",
        protocol="http",
        ip="192.168.1.20",
        port=80,
        status=DeviceStatus.CONFIGURED,
        device_type="generic",
    ))
    return config


@pytest.fixture
def ctrl():
    return DeviceController()


# ── Tool listing ────────────────────────────────────────────────────────────


class TestListTools:
    def test_returns_expected_tool_names(self, cfg):
        tools = list_tools(cfg)
        names = {t.name for t in tools}
        assert names == {
            "iotcli_list_devices",
            "iotcli_get_status",
            "iotcli_status_all",
            "iotcli_turn_on",
            "iotcli_turn_off",
            "iotcli_set_property",
        }

    def test_device_enum_populated(self, cfg):
        tools = list_tools(cfg)
        status_tool = next(t for t in tools if t.name == "iotcli_get_status")
        device_param = status_tool.inputSchema["properties"]["device"]
        assert "enum" in device_param
        assert "test-ac" in device_param["enum"]
        assert "test-light" in device_param["enum"]

    def test_empty_config_no_enum(self, tmp_path):
        empty_cfg = ConfigManager(config_dir=tmp_path / "empty")
        tools = list_tools(empty_cfg)
        status_tool = next(t for t in tools if t.name == "iotcli_get_status")
        device_param = status_tool.inputSchema["properties"]["device"]
        assert "enum" not in device_param

    def test_all_tools_have_input_schema(self, cfg):
        for tool in list_tools(cfg):
            assert tool.inputSchema is not None
            assert tool.inputSchema["type"] == "object"


# ── Tool handlers ───────────────────────────────────────────────────────────


class TestToolHandlers:
    @pytest.mark.asyncio
    async def test_list_devices(self, cfg, ctrl):
        result = await handle_tool("iotcli_list_devices", {}, cfg, ctrl)
        assert len(result) == 1
        data = json.loads(result[0].text)
        assert "devices" in data
        names = {d["name"] for d in data["devices"]}
        assert names == {"test-light", "test-ac"}

    @pytest.mark.asyncio
    async def test_unknown_device_returns_error(self, cfg, ctrl):
        result = await handle_tool(
            "iotcli_get_status", {"device": "nonexistent"}, cfg, ctrl
        )
        data = json.loads(result[0].text)
        assert data["success"] is False
        assert "not found" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, cfg, ctrl):
        result = await handle_tool("iotcli_nope", {}, cfg, ctrl)
        data = json.loads(result[0].text)
        assert data["success"] is False
        assert "unknown tool" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_set_missing_property_returns_error(self, cfg, ctrl):
        result = await handle_tool(
            "iotcli_set_property",
            {"device": "test-light", "value": 50},
            cfg, ctrl,
        )
        data = json.loads(result[0].text)
        assert data["success"] is False
        assert "property" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_turn_on_missing_device_returns_error(self, cfg, ctrl):
        result = await handle_tool("iotcli_turn_on", {}, cfg, ctrl)
        data = json.loads(result[0].text)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_turn_off_missing_device_returns_error(self, cfg, ctrl):
        result = await handle_tool("iotcli_turn_off", {"device": ""}, cfg, ctrl)
        data = json.loads(result[0].text)
        assert data["success"] is False


# ── Resources ───────────────────────────────────────────────────────────────


class TestResources:
    def test_list_resources_includes_devices_and_schema(self, cfg):
        resources = list_resources(cfg)
        uris = {str(r.uri) for r in resources}
        assert "iotcli://devices" in uris
        assert "iotcli://schema" in uris

    def test_list_resources_includes_per_device(self, cfg):
        resources = list_resources(cfg)
        uris = {str(r.uri) for r in resources}
        assert "iotcli://device/test-light" in uris
        assert "iotcli://device/test-ac" in uris

    def test_read_devices_resource(self, cfg):
        raw = read_resource("iotcli://devices", cfg)
        data = json.loads(raw)
        assert "devices" in data
        names = {d["name"] for d in data["devices"]}
        assert "test-light" in names

    def test_read_device_detail(self, cfg):
        raw = read_resource("iotcli://device/test-light", cfg)
        data = json.loads(raw)
        assert data["name"] == "test-light"
        assert data["protocol"] == "http"
        assert "settable_properties" in data

    def test_read_unknown_device(self, cfg):
        raw = read_resource("iotcli://device/nope", cfg)
        data = json.loads(raw)
        assert "error" in data

    def test_read_schema_resource(self, cfg):
        raw = read_resource("iotcli://schema", cfg)
        data = json.loads(raw)
        assert "devices" in data
        assert "test-light" in data["devices"]

    def test_read_unknown_uri(self, cfg):
        raw = read_resource("iotcli://unknown", cfg)
        data = json.loads(raw)
        assert "error" in data


# ── Server wiring ───────────────────────────────────────────────────────────


class TestServer:
    def test_create_server_returns_server(self, cfg):
        server = create_server(cfg)
        assert server is not None

    def test_create_server_default_config(self):
        server = create_server()
        assert server is not None
