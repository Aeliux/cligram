from telethon import TelegramClient

from .. import Application, CustomSession, exceptions, utils
from . import telegram


async def login(app: Application):
    """Login to a new Telegram session."""
    exists = False
    try:
        utils.get_session(app.config, create=False)
        exists = True
    except exceptions.SessionNotFoundError:
        pass

    if exists:
        app.console.print("[red]Session already exists.[/red]")
        return

    app.status.update("Logging in to Telegram...")
    session: CustomSession = utils.get_session(app.config, create=True)

    await telegram.setup(app=app, callback=login_callback, session=session)


async def login_callback(app: Application, client: TelegramClient):
    """Callback for login task."""
    app.console.print("[green]Logged in successfully![/green]")


async def logout(app: Application):
    """Logout from the current Telegram session."""
    await telegram.setup(app=app, callback=logout_callback, disconnect_expected=True)


async def logout_callback(app: Application, client: TelegramClient):
    """Callback for logout task."""
    app.status.update("Logging out...")
    res = await client.log_out()
    if not res:
        app.console.print("[red]Logout failed![/red]")
        return

    app.console.print("[green]Logged out successfully![/green]")
