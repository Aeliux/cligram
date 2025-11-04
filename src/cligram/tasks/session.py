import asyncio

from telethon import TelegramClient

from .. import Application, CustomSession, SessionNotFoundError, utils
from . import telegram


async def login(app: Application, shutdown_event: asyncio.Event):
    """Login to a new Telegram session."""
    exits = False
    try:
        session: CustomSession = utils.get_session(app.config, create=False)
        exits = True
    except SessionNotFoundError:
        pass

    if exits:
        app.console.print("[red]Session already exists.[/red]")
        return

    app.status.update("Logging in to Telegram...")
    session: CustomSession = utils.get_session(app.config, create=True)

    await telegram.setup(
        app=app, shutdown_event=shutdown_event, session=session, callback=login_callback
    )


async def login_callback(
    app: Application, shutdown_event: asyncio.Event, client: TelegramClient
):
    """Callback for login task."""
    app.console.print("[green]Logged in successfully![/green]")
