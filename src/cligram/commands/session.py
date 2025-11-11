import typer

from ..app import Application
from ..config import Config
from ..session import CustomSession

app = typer.Typer(
    help="Manage Telegram sessions",
)


@app.command("login")
def login(
    ctx: typer.Context,
    session: str = typer.Argument(
        None,
        help="Session name for authentication",
    ),
):
    """Login to a Telegram session."""
    from .. import tasks

    config: Config = ctx.obj["cligram.init:core"]()
    if session:
        config.telegram.session = session
    app: Application = ctx.obj["cligram.init:app"]()
    app.start(tasks.session.login)


@app.command("list")
def list_sessions(
    ctx: typer.Context,
):
    """List all available Telegram sessions."""
    ctx.obj["cligram.init:core"]()
    sessions = CustomSession.list_sessions()
    if sessions:
        typer.echo("Available sessions:")
        for s in sessions:
            typer.echo(s)
    else:
        typer.echo("No sessions found.")
    raise typer.Exit()
