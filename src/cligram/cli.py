import json
import time
from pathlib import Path
from typing import List, Optional

import typer

from . import commands
from .app import Application
from .config import Config, WorkMode, find_config_file
from .logger import setup_logger


def validate_config_path(value: Path) -> Path:
    """
    Validate configuration file path.

    Args:
        value: Path to validate

    Returns:
        Path: Valid configuration file path

    Raises:
        typer.BadParameter: If path doesn't exist or points to directory
    """
    resolved_path = value.resolve()
    if not resolved_path.exists():
        raise typer.BadParameter(f"Config file does not exist: {resolved_path}")
    if resolved_path.is_dir():
        raise typer.BadParameter(f"Config path points to a directory: {resolved_path}")

    return resolved_path


app = typer.Typer(
    help="CLI based telegram client",
    add_completion=False,
)

app.add_typer(commands.config.app, name="config")
app.add_typer(commands.session.app, name="session")
app.add_typer(commands.proxy.app, name="proxy")


@app.command()
def run(
    ctx: typer.Context,
    test: bool = typer.Option(
        False, "-t", "--test", help="Run in test mode without sending actual messages"
    ),
    rapid_save: bool = typer.Option(
        False, "--rapid-save", help="Enable rapid state saving to disk"
    ),
    mode: WorkMode = typer.Option(
        WorkMode.FULL.value, "-m", "--mode", help="Operation mode"
    ),
    session: Optional[str] = typer.Option(
        None, "-s", "--session", help="Telethon session name for authentication"
    ),
    limit: Optional[int] = typer.Option(
        None, "-l", "--limit", help="Maximum number of messages to process per group"
    ),
    exclude: Optional[Path] = typer.Option(
        None,
        "-e",
        "--exclude",
        help="JSON file with usernames to exclude from processing",
    ),
):
    """Telegram message scanner and forwarder."""
    config: Config = ctx.obj["g_load_config"]()
    if test:
        config.scan.test = True
    if rapid_save:
        config.app.rapid_save = True
    if mode:
        config.app.mode = mode
    if session:
        config.telegram.session = session
    if limit is not None:
        config.scan.limit = limit
    if exclude:
        config.exclusions = json.load(exclude.open("r"))
    app = Application(config=config)
    app.start()


@app.command("interactive")
def interactive(
    ctx: typer.Context,
    session: Optional[str] = typer.Option(
        None,
        "-s",
        "--session",
        help="Session name for authentication",
    ),
):
    """Run the application in interactive mode."""
    from .tasks import interactive

    config: Config = ctx.obj["g_load_config"]()
    if session:
        config.telegram.session = session

    app: Application = ctx.obj["g_load_app"]()
    app.start(interactive.main)


@app.command("test")
def test_command(
    ctx: typer.Context,
):
    """Development test command."""
    from rich.box import SIMPLE
    from rich.columns import Columns
    from rich.console import Console
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table

    console = Console()

    table = Table.grid(padding=(1, 5))
    table.add_column(style="cyan")
    table.add_column(style="magenta")
    table.add_row("Item 1", "This is the first item.")
    table.add_row("Item 2sssssssssss", "This is the second item.")
    console.print(table)


@app.callback()
def callback(
    ctx: typer.Context,
    config: Path = typer.Option(
        None,
        "-c",
        "--config",
        help="Path to JSON configuration file",
    ),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", help="Enable detailed debug logging output to console"
    ),
    overrides: Optional[List[str]] = typer.Option(
        None,
        "-o",
        "--override",
        help="Override config values using dot notation (e.g., app.verbose=true)",
    ),
):
    """
    CLI entry point for cligram application.
    """
    ctx.obj = {}

    def setup() -> Config:
        nonlocal config, verbose, overrides

        if Config.get_config(raise_if_failed=False) is not None:
            return Config.get_config()

        config = config or find_config_file(raise_error=True)
        loaded_config = Config.from_file(config, overrides=overrides)
        if verbose:
            loaded_config.app.verbose = True

        setup_logger(
            verbose=loaded_config.app.verbose,
            log_file=loaded_config.base_path
            / "logs"
            / time.strftime("%Y-%m-%d.log", time.localtime()),
        )

        return loaded_config

    ctx.obj["g_load_config"] = setup

    def load_app() -> Application:
        from .app import Application

        cfg = ctx.obj["g_load_config"]()
        return Application(config=cfg)

    ctx.obj["g_load_app"] = load_app


def main():
    app()
