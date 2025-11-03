from pathlib import Path
from typing import List, Optional

import typer

from .config import Config, WorkMode
from .session import CustomSession


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
        typer.echo("Config file does not exist, creating default config...")

        # create a default config file
        Config.create_default_config(resolved_path)
        typer.echo(f"Created default config file at: {resolved_path}")
        typer.echo(
            "Please review and update the configuration file as needed before running again."
        )
        raise typer.Exit()
    if resolved_path.is_dir():
        raise typer.BadParameter(f"Config path points to a directory: {resolved_path}")

    return resolved_path


app = typer.Typer(
    help="Telegram message scanner and forwarder",
    add_completion=False,
)


@app.command()
def run(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False, "-v", "--verbose", help="Enable detailed debug logging output to console"
    ),
    test: bool = typer.Option(
        False, "-t", "--test", help="Run in test mode without sending actual messages"
    ),
    list: bool = typer.Option(False, "--list", help="List all available sessions"),
    rapid_save: bool = typer.Option(
        False, "--rapid-save", help="Enable rapid state saving to disk"
    ),
    config_path: Path = typer.Option(
        Path("config.json"),
        "-c",
        "--config",
        help="Path to JSON configuration file with all settings",
        callback=validate_config_path,
    ),
    print_config: bool = typer.Option(
        False, "--print-config", help="Print the loaded configuration and exit"
    ),
    query: Optional[str] = typer.Option(
        None,
        "--query",
        help="Query a config value using dot notation (e.g., app.verbose)",
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
    proxy: Optional[str] = typer.Option(
        None,
        "-p",
        "--proxy",
        help="Proxy URL (mtproto:// or socks5://) that overrides config",
    ),
    exclude: Optional[Path] = typer.Option(
        None,
        "-e",
        "--exclude",
        help="JSON file with usernames to exclude from processing",
    ),
    overrides: Optional[List[str]] = typer.Option(
        None,
        "-o",
        "--override",
        help="Override config values using dot notation (e.g., app.verbose=true)",
    ),
):
    """Telegram message scanner and forwarder."""
    args = {
        k: v
        for k, v in locals().items()
        if k not in ["ctx", "Application"] and v is not None
    }
    config = Config.from_file(config_path=config_path, cli_args=args)

    if print_config:
        flatted = Config._flatten_dict(config.to_dict())
        for key, value in flatted.items():
            typer.echo(f"{key}={value}")
        raise typer.Exit()
    elif query:
        result = config.get_nested_value(query)
        typer.echo(f"{query}={result}")
        raise typer.Exit()
    elif list:
        sessions = CustomSession.list_sessions()
        if sessions:
            typer.echo("Available sessions:")
            for s in sessions:
                typer.echo(f" - {s}")
        else:
            typer.echo("No sessions found.")
        raise typer.Exit()

    from .app import Application

    app = Application(config=config, **args)
    app.start()


def main():
    app()
