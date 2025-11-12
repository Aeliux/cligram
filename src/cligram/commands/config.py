from pathlib import Path

import typer

from .. import GLOBAL_CONFIG_PATH, Config

app = typer.Typer(help="Configuration management")


@app.command("create")
def create_config(
    path: Path = typer.Argument(
        Path("config.json"), help="Path to create the configuration file at"
    ),
    glb: bool = typer.Option(
        False,
        "--global",
        "-g",
        help="Create global configuration in user home directory",
    ),
    no_interactive: bool = typer.Option(
        False, "--no-interactive", "-n", help="Do not prompt user"
    ),
):
    """Create a default configuration file."""
    if glb:
        path = GLOBAL_CONFIG_PATH

    path = path.resolve()
    if path.exists():
        typer.echo(f"Configuration file already exists at: {path}")
        raise typer.Exit(1)

    def_config = Config()

    if not no_interactive:
        typer.echo("Creating default configuration. Press Enter to accept defaults.")
        api_id = typer.prompt(
            "Telegram API ID", default=str(def_config.telegram.api.id)
        )
        api_hash = typer.prompt(
            "Telegram API Hash", default=def_config.telegram.api.hash
        )
        def_config.telegram.api.id = int(api_id)
        def_config.telegram.api.hash = api_hash

    def_config.save(path)
    typer.echo(f"Created default configuration file at: {path}")


@app.command("list")
def list_configs(
    ctx: typer.Context,
):
    """List all available configuration files."""
    config: Config = ctx.obj["cligram.init:core"]()
    flatted = Config._flatten_dict(config.to_dict())
    for key, value in flatted.items():
        typer.echo(f"{key}={value}")
    raise typer.Exit()


@app.command("get")
def get_config(
    ctx: typer.Context, key: str = typer.Argument(help="Configuration key to retrieve")
):
    """Get a specific configuration value."""
    config: Config = ctx.obj["cligram.init:core"]()
    value = config.get_nested_value(key)
    if value is not None:
        typer.echo(f"{key}={value}")
    else:
        typer.echo(f"Configuration key not found: {key}")
    raise typer.Exit()


@app.command("set")
def set_config(
    ctx: typer.Context,
    key: str = typer.Argument(help="Configuration key to set"),
    value: str = typer.Argument(help="Configuration value to set"),
):
    """Set a specific configuration value."""
    config: Config = ctx.obj["cligram.init:core"]()
    parsed_value = config._parse_value(value)
    config.set_nested_value(key, parsed_value)
    config.save()
    nvalue = config.get_nested_value(key)
    typer.echo(f"{key}={nvalue}")
