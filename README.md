# iotcli

<p align="center">
  <b>Give your AI agent hands.</b><br>
  One CLI to rule them all. Discover, configure, and control IoT devices across protocols.<br>
  Built for AI agents, loved by humans.
</p>

<p align="center">
  <a href="https://pypi.org/project/iotcli/"><img src="https://img.shields.io/pypi/v/iotcli?style=flat-square&color=blue" alt="PyPI version"></a>
  <a href="https://pypi.org/project/iotcli/"><img src="https://img.shields.io/pypi/pyversions/iotcli?style=flat-square" alt="Python versions"></a>
  <a href="https://github.com/fomyio/iotcli/actions"><img src="https://img.shields.io/github/actions/workflow/status/fomyio/iotcli/ci.yml?style=flat-square&logo=github" alt="CI"></a>
  <a href="https://codecov.io/gh/fomyio/iotcli"><img src="https://img.shields.io/codecov/c/github/fomyio/iotcli?style=flat-square&logo=codecov" alt="Coverage"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"></a>
  <a href="PRIVACY.md"><img src="https://img.shields.io/badge/privacy-local%20only-success?style=flat-square" alt="Privacy"></a>
</p>

<p align="center">
  <a href="#install">Install</a> &bull;
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#ai-agent-integration">AI Integration</a> &bull;
  <a href="#supported-protocols">Protocols</a> &bull;
  <a href="#architecture">Architecture</a>
</p>

---

## What is iotcli?

iotcli is a universal IoT device control CLI. It unifies smart-home devices behind a single, predictable interface — so you (or your AI agent) can control lights, AC units, feeders, and sensors without memorizing protocol quirks.

**Key principles:**
- **One command shape** for every device — `on`, `off`, `status`, `set`
- **Protocol-agnostic** — Tuya, miIO, MQTT, HTTP, LG ThinQ, and more
- **AI-native** — JSON mode, skill files, and an MCP server for Claude Desktop / Cursor / Zed
- **Privacy-first** — everything local, credentials encrypted, no telemetry

## Install

```bash
# Global install via pipx (recommended — no venv needed)
pipx install git+https://github.com/fomyio/iotcli.git

# Or with MCP support for Claude Desktop / Cursor
pipx install git+https://github.com/fomyio/iotcli.git[mcp]

# From source
git clone https://github.com/fomyio/iotcli.git
cd iotcli
pip install -e ".[dev]"
```

> Requires Python 3.10+

## Quick Start

```bash
# Interactive setup wizard (Rich TUI)
iotcli setup

# Discover devices on your network
iotcli discover --network 192.168.1.0/24

# Add a device
iotcli add --name living-room-light --protocol miio \
    --ip 192.168.1.100 --token <32chars>

# Control
iotcli control on living-room-light
iotcli control status living-room-light
iotcli control set living-room-light brightness=80

# AI agent mode (structured JSON)
iotcli --json list
iotcli --json control status living-room-light
iotcli --json status-all
```

## Demo

```text
$ iotcli list
╭─────────── Devices ───────────╮
│ Name              Protocol  IP            │
│ living-room-light miio      192.168.1.100 │
│ feeder            tuya      192.168.1.4   │
│ lg-ac             lgac      (cloud)       │
╰───────────────────────────────╯

$ iotcli control status lg-ac
╭─── lg-ac — online ───╮
│   power: POWER_OFF   │
│   mode: HEAT         │
│   fan_speed: HIGH    │
│   current_temp: 20.5 │
│   target_temp: 25    │
╰──────────────────────╯

$ iotcli --json control on feeder
{"success": true, "device": "feeder", "action": "on"}
```

## Supported Protocols

| Protocol | Devices | Connection |
|----------|---------|------------|
| `miio` | Xiaomi / Yeelight | Local (UDP) |
| `tuya` | Tuya-based (lights, plugs, etc.) | Local (TCP) |
| `mqtt` | Zigbee / Aqara via MQTT broker | Local (TCP) |
| `http` | ESPHome / Tasmota | Local (HTTP) |
| `lgac` | LG Air Conditioner (ThinQ) | Cloud (HTTPS) |

### Tuya Profiles

| Profile | Devices | Special Actions |
|---------|---------|-----------------|
| `generic` | Any Tuya device | power on/off |
| `light` | Smart bulbs | brightness, color_temperature, color |
| `switch` | Smart plugs | power, countdown |
| `petfeeder` | ROJECO / Tuya feeders | portions, quick_feed, slow_feed, light |

```bash
iotcli add --name feeder --protocol tuya --profile petfeeder \
    --ip 192.168.1.4 --device-id <id> --local-key <key> --version 3.4
```

## AI Agent Integration

iotcli was built from the ground up for AI agents. Every command supports `--json` for structured, parseable output.

### Skill Files

Generate per-device skill files so your agent knows exactly what each device can do:

```bash
iotcli skills generate
```

Files created in `~/.iotcli/skills/`:
- `<device>/SKILL.md` — per-device capability doc (OpenClaw-compatible)
- `iotcli.tools.json` — OpenAI/Anthropic tool schema
- `iotcli.skill.yaml` — legacy global skill spec
- `system_prompt.md` — ready-to-use agent system prompt

### MCP Server (Claude Desktop / Cursor / Zed)

Connect iotcli directly to your AI assistant via the Model Context Protocol:

```bash
# Install with MCP support
pip install iotcli[mcp]

# Start the server
iotcli serve mcp
```

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "iotcli": {
      "command": "iotcli",
      "args": ["serve", "mcp"]
    }
  }
}
```

Once connected, Claude can list devices, check status, turn them on/off, and set properties — all through structured tool calls with per-device enums and value validation. No copy-pasting commands.

### Agent Workflow

```bash
# 1. Discover what's available
iotcli --json list

# 2. Check state before acting
iotcli --json control status "living-room-light"

# 3. Act
iotcli --json control on "living-room-light"
iotcli --json control set "living-room-light" "brightness=80"
```

## Architecture

```text
src/iotcli/
├── core/           # Device model, protocol registry, controller
├── protocols/      # Self-registering protocol handlers
├── config/         # YAML config + Fernet credential vault
├── discovery/      # Async multi-protocol network scanner
├── tui/            # Rich + InquirerPy interactive wizard
├── cli/            # Click commands (discover, control, device, config, skills)
├── skills/         # Jinja2-based AI agent skill generator
└── mcp/            # MCP server for Claude Desktop / Cursor / Zed
```

**Design decisions:**
- **Protocol registry** (`core/registry.py`): Decorator-based self-registration. No hardcoded mappings.
- **Device model** (`core/device.py`): Dataclass with `slugify()` for normalized names.
- **Credentials**: Fernet-encrypted vault, never in `devices.yaml`. Key stored at `0600`.
- **Extensible**: Add a protocol by implementing `BaseProtocol` — the CLI, wizard, and skill generator pick it up automatically.

## Security

- Credentials are **never** stored in config files
- Secrets encrypted with Fernet at `~/.iotcli/credentials/`
- Encryption key has `0600` permissions (owner-only)
- No telemetry, no analytics, no cloud dependency
- Fully open source — inspect exactly what runs on your machine

See [PRIVACY.md](PRIVACY.md) for details.

## Extending — Add a New Protocol

```python
# src/iotcli/protocols/myproto.py

@register_protocol("myproto")
class MyProtocol(BaseProtocol):
    meta = ProtocolMeta(
        name="myproto",
        display_name="My Protocol",
        default_port=9999,
        required_credentials=["api_key"],
        ...
    )

    def connect(self) -> bool: ...
    def disconnect(self) -> None: ...
    def turn_on(self) -> bool: ...
    def turn_off(self) -> bool: ...
    def get_status(self) -> dict: ...
    def set_value(self, prop, value) -> bool: ...
```

Add one import in `protocols/__init__.py` — the CLI, wizard, and skill generator pick it up automatically.

## License

MIT

---

<p align="center">
  Made with passion for AI agents and smart homes.
</p>
