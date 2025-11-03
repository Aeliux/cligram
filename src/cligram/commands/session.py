import typer

from ..config import Config
from ..session import CustomSession

app = typer.Typer(
    help="Manage Telegram sessions",
)


@app.command("list")
def list_sessions(
    ctx: typer.Context,
):
    """List all available Telegram sessions."""
    ctx.obj["g_load_config"]()
    sessions = CustomSession.list_sessions()
    if sessions:
        typer.echo("Available sessions:")
        for s in sessions:
            typer.echo(s)
    else:
        typer.echo("No sessions found.")
    raise typer.Exit()
