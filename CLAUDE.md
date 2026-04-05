# CLAUDE.md

## Development Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run
iotcli --help
python -m iotcli --help

# Test
pytest
```

## Architecture

```text
src/iotcli/
├── core/           # Device model, protocol registry, controller, exceptions
├── protocols/      # Self-registering protocol handlers (@register_protocol)
├── config/         # YAML config + Fernet credential vault
├── discovery/      # Async multi-protocol network scanner
├── tui/            # Rich + InquirerPy interactive wizard
├── cli/            # Click commands (discover, control, device, config, skills)
└── skills/         # Jinja2-based AI agent skill generator
```

### Adding a New Protocol

1. Create `src/iotcli/protocols/myproto.py`
2. Use `@register_protocol("myproto")` decorator
3. Define `meta = ProtocolMeta(...)` class attribute
4. Implement: `connect`, `disconnect`, `turn_on`, `turn_off`, `get_status`, `set_value`
5. Add import in `src/iotcli/protocols/__init__.py`

That's it — CLI, wizard, and skill generator pick it up automatically.

### Key Design Decisions

- **Protocol registry** (`core/registry.py`): Decorator-based, protocols self-register on import. No hardcoded mappings.
- **Device model** (`core/device.py`): Dataclass, not raw dicts. `slugify()` auto-normalizes names (lowercase, hyphens).
- **Credentials**: Never stored in `devices.yaml`. Fernet-encrypted vault in `~/.iotcli/credentials/`.
- **Tuya profiles**: PetFeeder, Light, Switch are profiles within the Tuya protocol, not separate protocol classes.
- **Output**: `cli/output.py` handles JSON vs human-readable. TUI commands use Rich panels/tables.
- **Skills**: Generated from protocol metadata + Jinja2 templates. `iotcli skills generate` creates per-device skill docs.

### Config Location

`~/.iotcli/` — `devices.yaml` (no secrets), `credentials/*.enc` (Fernet), `.key` (encryption key, 0600).
