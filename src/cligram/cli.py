"""CLI entry point."""

import asyncio
import datetime
import logging
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

import typer
from click import ClickException
from dotenv import load_dotenv

from . import DEFAULT_PATH, commands, exceptions, utils
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


@app.command("export")
def export(
    ctx: typer.Context,
    output: Optional[Path] = typer.Argument(
        None,
        help="Output path for exported data, defaults to stdout",
    ),
    password: Optional[str] = typer.Option(
        None,
        "-p",
        "--password",
        help="Password for encrypting exported data",
    ),
    no_config: bool = typer.Option(
        False,
        "--no-config",
        help="Exclude the current configuration from the export",
    ),
    export_dotenv: bool = typer.Option(
        False,
        "--export-dotenv",
        help="Include the .env file in the export, only if environment variables are used for API credentials",
    ),
    exported_sessions: List[str] = typer.Option(
        [],
        "--session",
        help="Specific session names to include in the export, can be used multiple times."
        " They must be visible in session list command.",
    ),
    exported_states: List[str] = typer.Option(
        [],
        "--state",
        help="Specific state names to include in the export, can be used multiple times",
    ),
    all_sessions: bool = typer.Option(
        False,
        "--all-sessions",
        help="Include all sessions in the export",
    ),
    all_states: bool = typer.Option(
        False,
        "--all-states",
        help="Include all states in the export",
    ),
    all_data: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Export everything (sessions, states, and configuration)",
    ),
):
    """Export cligram data."""
    from .tasks import transfer

    config: "Config" = ctx.obj["cligram.init:core"]()
    config.temp["cligram.transfer:export"] = transfer._ExportConfig(
        export_config=not no_config,
        export_dotenv=export_dotenv or all_data,
        exported_sessions="*" if all_sessions or all_data else exported_sessions,
        exported_states="*" if all_states or all_data else exported_states,
        path=output,
        password=password,
    )

    app: "Application" = ctx.obj["cligram.init:app"]()
    app.start(transfer.export)


@app.command("import")
def import_data(
    ctx: typer.Context,
    input: str = typer.Argument(
        help="Input data for import, can be a file path or base64 string",
    ),
    base64: bool = typer.Option(
        False,
        "-b",
        "--base64",
        help="Indicates that the input is a base64 encoded string",
    ),
    password: Optional[str] = typer.Option(
        None,
        "-p",
        "--password",
        help="Password for decrypting the imported data",
    ),
):
    """Import cligram data."""
    from .tasks import transfer

    try:
        config: "Config" = ctx.obj["cligram.init:core"]()
    except Exception:
        from . import Config

        config = Config()
    cfg = config.temp["cligram.transfer:import"] = transfer._ImportConfig(
        input_value=input,
        is_data=base64,
        password=password,
    )

    asyncio.run(transfer.import_early(cfg=cfg))
    if cfg._need_exit:
        raise typer.Exit()

    app: "Application" = ctx.obj["cligram.init:app"]()
    app.config.temp["cligram.transfer:import"] = cfg
    app.start(transfer.import_data)


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
    setup_preinit_logger()

    dotenv_paths = [Path(".env"), DEFAULT_PATH / ".env", Path.home() / ".cligram.env"]
    for dotenv_path in dotenv_paths:
        if dotenv_path.is_file():
            logger.info(f"Loading environment variables from: {dotenv_path}")
            load_dotenv(dotenv_path)

    app()
