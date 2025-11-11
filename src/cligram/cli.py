import logging
from pathlib import Path
from typing import List, Optional

import typer
from click import FileError

from . import Application, Config, ScanMode, commands, utils
from .config import find_config_file
from .logger import setup_logger, setup_preinit_logger

logger = logging.getLogger(__name__)


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
    mode: ScanMode = typer.Option(
        ScanMode.FULL.value, "-m", "--mode", help="Operation mode"
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
    typer.echo("The 'run' command is currently under development.")
    typer.Exit(1)

    # config: Config = ctx.obj["g_load_config"]()
    # if test:
    #     config.scan.test = True
    # if rapid_save:
    #     config.scan.rapid_save = True
    # if mode:
    #     config.scan.mode = mode
    # if session:
    #     config.telegram.session = session
    # if limit is not None:
    #     config.scan.limit = limit
    # if exclude:
    #     config.exclusions = json.load(exclude.open("r"))
    # app = Application(config=config)
    # app.start()


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


@app.command("info")
def info():
    """Display information about cligram and current environment."""
    from . import __version__

    typer.echo(f"cligram version: {__version__}")

    device_info = utils.get_device_info()
    typer.echo(f"Platform: {device_info.platform.value}")
    typer.echo(f"Architecture: {device_info.architecture.value}")
    typer.echo(f"Title: {device_info.title}")
    typer.echo(f"OS Name: {device_info.name}")
    typer.echo(f"OS Version: {device_info.version}")
    typer.echo(f"Device Model: {device_info.model}")
    typer.echo(
        f"Environments: {', '.join(env.value for env in device_info.environments)}"
    )


@app.callback()
def callback(
    ctx: typer.Context,
    config: Optional[Path] = typer.Option(
        None,
        "-c",
        "--config",
        help="Path to JSON configuration file",
    ),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", help="Enable detailed debug logging output to console"
    ),
    overrides: List[str] = typer.Option(
        [],
        "-o",
        "--override",
        help="Override config values using dot notation (e.g., app.verbose=true)",
    ),
):
    """
    CLI entry point for cligram application.
    """
    setup_preinit_logger()

    logger.info("Starting cligram CLI")

    ctx.obj = {}

    def setup() -> Config:
        nonlocal config, verbose, overrides

        if Config.get_config(raise_if_failed=False) is not None:
            return Config.get_config()

        config = config or find_config_file(raise_error=True)
        if not config:
            raise FileError("Configuration file not found.")

        loaded_config = Config.from_file(config, overrides=overrides)
        if verbose and not loaded_config.app.verbose:
            loaded_config.overridden = True
            loaded_config.app.verbose = True

        logger.info("Configuration loaded successfully.")
        logger.info("pre-init complete, setting up logger")

        setup_logger(loaded_config)

        return loaded_config

    ctx.obj["g_load_config"] = setup

    def load_app() -> Application:
        from .app import Application

        cfg = ctx.obj["g_load_config"]()
        return Application(config=cfg)

    ctx.obj["g_load_app"] = load_app


def main():
    app()
