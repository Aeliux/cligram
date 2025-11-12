"""CLI entry point."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

import typer
from click import ClickException

from . import commands, exceptions, utils
from .logger import setup_logger, setup_preinit_logger

if TYPE_CHECKING:
    from . import Application, Config

logger = logging.getLogger(__name__)

app = typer.Typer(
    help="CLI based telegram client",
    add_completion=False,
    no_args_is_help=True,
    add_help_option=True,
    pretty_exceptions_show_locals=False,  # For security reasons
    pretty_exceptions_short=True,
)

app.add_typer(commands.config.app, name="config")
app.add_typer(commands.session.app, name="session")
app.add_typer(commands.proxy.app, name="proxy")


# @app.command()
# def run(
#     ctx: typer.Context,
#     test: bool = typer.Option(
#         False, "-t", "--test", help="Run in test mode without sending actual messages"
#     ),
#     rapid_save: bool = typer.Option(
#         False, "--rapid-save", help="Enable rapid state saving to disk"
#     ),
#     mode: ScanMode = typer.Option(
#         ScanMode.FULL.value, "-m", "--mode", help="Operation mode"
#     ),
#     session: Optional[str] = typer.Option(
#         None, "-s", "--session", help="Telethon session name for authentication"
#     ),
#     limit: Optional[int] = typer.Option(
#         None, "-l", "--limit", help="Maximum number of messages to process per group"
#     ),
#     exclude: Optional[Path] = typer.Option(
#         None,
#         "-e",
#         "--exclude",
#         help="JSON file with usernames to exclude from processing",
#     ),
# ):
#     """Telegram message scanner and forwarder."""
#     typer.echo("The 'run' command is currently under development.")
#     typer.Exit(1)

#     config: Config = ctx.obj["cligram.init:core"]()
#     if test:
#         config.scan.test = True
#     if rapid_save:
#         config.scan.rapid_save = True
#     if mode:
#         config.scan.mode = mode
#     if session:
#         config.telegram.session = session
#     if limit is not None:
#         config.scan.limit = limit
#     if exclude:
#         config.exclusions = json.load(exclude.open("r"))
#     app = Application(config=config)
#     app.start()


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

    config: "Config" = ctx.obj["cligram.init:core"]()
    if session:
        config.telegram.session = session
        config.overridden = True

    app: "Application" = ctx.obj["cligram.init:app"]()
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
    """CLI context setup."""
    setup_preinit_logger()

    logger.info("Starting cligram CLI")

    ctx.obj = {}
    ctx.obj["cligram.args:config"] = config
    ctx.obj["cligram.args:verbose"] = verbose
    ctx.obj["cligram.args:overrides"] = overrides

    ctx.obj["cligram.init:core"] = lambda: init(ctx)
    ctx.obj["cligram.init:app"] = lambda: init_app(ctx)


def init(ctx: typer.Context) -> "Config":
    """Initialize core components based on CLI context.

    Once this function is called, the pre-init stage is over,
    configuration is guaranteed to be loaded, logger is set up, and ready for use.

    Returns:
        Config: Loaded configuration instance.
    """
    from .config import Config, find_config_file

    lconfig = Config.get_config(raise_if_failed=False)
    if lconfig is not None:
        typer.echo(
            "[yellow]Warning:[/yellow] Configuration was already loaded. Using existing configuration."
        )
        return lconfig
    config: Optional[Path] = ctx.obj["cligram.args:config"]

    try:
        if not config:
            config = find_config_file(raise_error=True)
        loaded_config = Config.from_file(
            config, overrides=ctx.obj["cligram.args:overrides"]
        )
    except FileNotFoundError:
        raise ClickException(f"Configuration file not found: {config}")
    except exceptions.ConfigSearchError as e:
        raise ClickException(str(e))
    if ctx.obj["cligram.args:verbose"] and not loaded_config.app.verbose:
        loaded_config.overridden = True
        loaded_config.app.verbose = True

    logger.info("Configuration loaded successfully.")
    logger.info("pre-init complete.")

    setup_logger(loaded_config)

    return loaded_config


def init_app(ctx: typer.Context) -> "Application":
    """Safely initialize the main application instance.

    Ensures the core is initialized, then
    Initialize the main application instance based on CLI context.

    Returns:
        Application: Initialized application instance.
    """
    from . import Application

    cfg = ctx.obj["cligram.init:core"]()
    return Application(config=cfg)


def main():
    """Main entry point for the CLI."""
    app()
