# iotcli

**Give your AI agent hands — control any smart home device from the terminal.**

One CLI to rule them all. Discover, configure, and control IoT devices across protocols. Built for AI agents, loved by humans.

```text
$ iotcli control status lg-ac
╭─── lg-ac — online ───╮
│   power: POWER_OFF   │
│   mode: HEAT         │
│   fan_speed: HIGH    │
│   current_temp: 20.5 │
│   target_temp: 25    │
╰──────────────────────╯
```

## Install

```bash
# Global install (recommended — no venv needed, no package conflicts)
pipx install git+https://github.com/joeVenner/CLI-IoT.git

# Or from a local clone
git clone https://github.com/joeVenner/CLI-IoT.git
cd CLI-IoT
pipx install .
```

After install, `iotcli` is available system-wide. No activation, no venv.

## Quick Start

```bash
# Interactive setup wizard (Rich TUI)
iotcli setup

# Discover devices on your network
iotcli discover

# Add a device non-interactively
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

## Supported Protocols

| Protocol | Devices                          | Connection    |
| -------- | -------------------------------- | ------------- |
| `miio`   | Xiaomi / Yeelight                | Local (UDP)   |
| `tuya`   | Tuya-based (lights, plugs, etc.) | Local (TCP)   |
| `mqtt`   | Zigbee / Aqara via MQTT broker   | Local (TCP)   |
| `http`   | ESPHome / Tasmota                | Local (HTTP)  |
| `lgac`   | LG Air Conditioner (ThinQ)       | Cloud (HTTPS) |

### Tuya Device Profiles

| Profile      | Devices               | Special Actions                        |
| ------------ | --------------------- | -------------------------------------- |
| `generic`    | Any Tuya device       | power on/off                           |
| `light`      | Smart bulbs           | brightness, color_temperature, color   |
| `switch`     | Smart plugs           | power, countdown                       |
| `petfeeder`  | ROJECO / Tuya feeders | portions, quick_feed, slow_feed, light |

```bash
iotcli add --name feeder --protocol tuya --profile petfeeder \
    --ip 192.168.1.4 --device-id <id> --local-key <key> --version 3.4
```

## AI Agent Integration

Every command supports `--json` for structured output. Feed your agent the generated skill files and it knows how to control your home.

```bash
# Generate skill files for all configured devices
iotcli skills generate

# Files created in ~/.iotcli/skills/:
#   iotcli.skill.yaml     — global tool spec with all devices
#   system_prompt.md      — ready-to-use agent system prompt
#   <device>.skill.md     — per-device capability doc
```

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

## Security

- Credentials are **never** stored in config files
- Secrets encrypted with Fernet at `~/.iotcli/credentials/`
- Encryption key has `0600` permissions (owner-only)

## License

MIT
