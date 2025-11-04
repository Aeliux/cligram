import typer

from .. import Application, Config

app = typer.Typer(
    help="Run interactive telegram session",
)


@app.command()
def run(
    ctx: typer.Context,
    session: str = typer.Option(
        None,
        "-s",
        "--session",
        help="Session name for authentication",
    ),
):
    """Start an interactive telegram session."""
    from .. import tasks

    config: Config = ctx.obj["g_load_config"]()
    if session:
        config.telegram.session = session

    app: Application = ctx.obj["g_load_app"]()
    app.start(tasks.interactive.main)
