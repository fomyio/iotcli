"""Unified output handler — single place for JSON vs human-readable output."""

from __future__ import annotations

import json
import sys
from typing import Any

import click
from tabulate import tabulate


class Output:
    """Context-aware output that switches between JSON and human-readable."""

    def __init__(self, json_mode: bool = False):
        self.json_mode = json_mode

    # -- JSON helpers ---------------------------------------------------------

    def json_out(self, data: Any) -> None:
        click.echo(json.dumps(data, indent=2, default=str))

    def json_success(self, data: dict | None = None) -> None:
        payload: dict[str, Any] = {"success": True}
        if data:
            payload.update(data)
        self.json_out(payload)

    def json_error(self, message: str, exit_code: int = 1) -> None:
        click.echo(json.dumps({"success": False, "error": message}), err=True)
        sys.exit(exit_code)

    # -- human helpers --------------------------------------------------------

    def echo(self, msg: str) -> None:
        if not self.json_mode:
            click.echo(msg)

    def table(self, rows: list[list], headers: list[str]) -> None:
        if not self.json_mode:
            click.echo(tabulate(rows, headers=headers, tablefmt="simple"))

    # -- combined (smart) -----------------------------------------------------

    def success(self, message: str, data: dict | None = None) -> None:
        if self.json_mode:
            self.json_success(data)
        else:
            click.echo(message)

    def error(self, message: str, exit_code: int = 1) -> None:
        if self.json_mode:
            self.json_error(message, exit_code)
        else:
            click.echo(f"Error: {message}", err=True)
            sys.exit(exit_code)

    def device_status(self, name: str, status: dict[str, Any]) -> None:
        if self.json_mode:
            self.json_out({"device": name, **status})
            return
        online = status.get("online", False)
        icon = "online" if online else "offline"
        click.echo(f"\n{name} — {icon}")
        if online:
            click.echo("-" * 40)
            for k, v in status.items():
                if k not in ("online", "dps"):
                    click.echo(f"  {k}: {v}")
        elif "error" in status:
            click.echo(f"  error: {status['error']}")
