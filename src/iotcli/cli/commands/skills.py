"""iotcli skills — generate / list / show AI agent skill files."""

from __future__ import annotations

import click

from iotcli.cli.output import Output
from iotcli.config.manager import ConfigManager


@click.group()
def skills():
    """AI agent skill management."""
    pass


@skills.command()
@click.argument("device_name", required=False)
@click.option("--output-dir", "-o", default=None, help="Output directory (default: ~/.iotcli/skills/)")
@click.pass_context
def generate(ctx, device_name, output_dir):
    """Generate AI agent skill files for devices."""
    out = Output(ctx.obj["json_output"])
    cfg: ConfigManager = ctx.obj["config"]

    from iotcli.skills.generator import SkillGenerator

    gen = SkillGenerator(cfg)

    if device_name:
        device = cfg.get_device_or_none(device_name)
        if not device:
            out.error(f"Device not found: {device_name}")
        result = gen.generate_device_skill(device, output_dir=output_dir)
        out.success(f"Skill generated: {result}", {"file": result})
    else:
        results = gen.generate_all(output_dir=output_dir)
        out.success(
            f"Generated {len(results)} skill file(s).",
            {"files": results},
        )


@skills.command("list")
@click.pass_context
def list_skills(ctx):
    """List generated skill files."""
    out = Output(ctx.obj["json_output"])
    cfg: ConfigManager = ctx.obj["config"]

    from iotcli.skills.generator import SkillGenerator

    gen = SkillGenerator(cfg)
    files = gen.list_skills()

    if out.json_mode:
        out.json_out({"skills": files})
    else:
        if not files:
            out.echo("No skill files generated yet. Run: iotcli skills generate")
            return
        out.echo(f"\nGenerated skills ({len(files)}):\n")
        for f in files:
            out.echo(f"  {f}")


@skills.command()
@click.argument("device_name")
@click.pass_context
def show(ctx, device_name):
    """Print a device's skill document to stdout."""
    out = Output(ctx.obj["json_output"])
    cfg: ConfigManager = ctx.obj["config"]

    from iotcli.skills.generator import SkillGenerator

    gen = SkillGenerator(cfg)
    content = gen.get_skill_content(device_name)

    if content is None:
        out.error(f"No skill found for '{device_name}'. Run: iotcli skills generate {device_name}")

    if out.json_mode:
        out.json_out({"device": device_name, "skill": content})
    else:
        click.echo(content)
