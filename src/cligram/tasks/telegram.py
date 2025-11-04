import asyncio
import logging
from typing import Callable, Optional

from rich.style import Style
from telethon import TelegramClient
from telethon.tl import functions
from telethon.tl.types import User

from .. import (
    Application,
    CustomSession,
    Proxy,
    ProxyManager,
    SessionNotFoundError,
    utils,
)

logger = None


def setup_logger():
    global logger
    logger = logging.getLogger("cligram.tasks.telegram")


async def setup(
    app: Application,
    shutdown_event: asyncio.Event,
    session: Optional[CustomSession] = None,
    proxy: Optional[Proxy] = None,
    callback: (
        Callable[[Application, asyncio.Event, TelegramClient], asyncio.Future] | None
    ) = None,
):
    """Setup Telegram client."""
    setup_logger()

    try:
        # Get session
        session = session or utils.get_session(app.config)

        if not proxy:
            # Test proxies and get working one
            app.status.update("Testing connections...")
            logger.info("Testing connections")
            proxy_manager = ProxyManager.from_config(app.config)
            await proxy_manager.test_proxies(shutdown_event=shutdown_event)
            proxy = proxy_manager.current_proxy

            if proxy:
                if proxy.is_direct:
                    logger.info("Using direct connection")
                else:
                    app.console.print(
                        f"Using {proxy.type.value} proxy: {proxy.host}:{proxy.port}"
                    )
                    logger.info(
                        f"Using proxy: [{proxy.type.name}] {proxy.host}:{proxy.port}"
                    )
            else:
                app.console.print("No working connection available, aborting")
                logger.error("No working connection available, aborting")
                return

        app.status.update("Initializing client...")
        # Create actual client with working connection
        client: TelegramClient = utils.get_client(
            config=app.config, proxy=proxy, session=session
        )

        app.status.update("Logging in...")
        logger.info(f"Logging in with {client.session.filename} session")

        def _phone_callback():
            app.status.stop()
            return input("Please enter your phone (or bot token): ")

        await client.start(phone=_phone_callback)
        app.status.start()
        # Continue with client operations
        if shutdown_event.is_set():
            return

        app.status.update("Fetching account information...")
        logger.debug("Fetching account information")
        me: User = await client.get_me()

        if me.first_name and me.last_name:
            name = f"{me.first_name} {me.last_name}"
        else:
            name = me.first_name

        app.status.update("Updating status...")
        logger.debug("Updating status to online")
        result = await client(functions.account.UpdateStatusRequest(offline=False))
        if not result:
            app.console.print(
                "Failed to set status to online", style=Style(color="red")
            )
            logger.error("Failed to set status to online")
        else:
            logger.debug("Status set to online successfully")

        app.console.print(f"Logged in as {name} (ID: {me.id})")
        logger.info(f"Logged in as {name} (ID: {me.id})")

        # Log detailed account info for debugging
        if app.config.app.verbose:
            logger.debug(f"Account ID: {me.id}")
            logger.debug(f"Full Name: {name}")
            logger.debug(f"Username: {me.username}")
            logger.debug(f"Phone: {me.phone}")

        # Show unread messages count
        app.status.update("Checking unread messages...")
        logger.debug("Checking for unread messages")
        total_unread = 0
        async for dialog in client.iter_dialogs(limit=50):
            logger.debug(f"Processing {dialog.name} ({dialog.id})")
            try:
                unread = int(getattr(dialog, "unread_count", 0) or 0)
            except Exception:
                unread = 0
            logger.debug(f"Unread count: {unread}")
            if unread <= 0:
                continue
            muted = utils.telegram._is_dialog_muted(dialog)
            logger.debug(f"Is muted: {muted}")
            if muted:
                continue
            total_unread += unread

        if total_unread > 0:
            app.console.print(
                f"You have {total_unread} unread messages",
                style=Style(color="yellow"),
            )
            logger.warning(f"You have {total_unread} unread messages")
        else:
            logger.debug("No unread messages")

        try:
            await callback(app, shutdown_event, client)
        finally:
            app.status.update("Shutting down client...")
            if not client.is_connected():
                logger.warning("Client disconnected unexpectedly")
                return

            logger.debug("Updating status to offline")
            app.status.update("Updating status...")
            result = await client(functions.account.UpdateStatusRequest(offline=True))
            if not result:
                app.console.print(
                    "Failed to set status to offline", style=Style(color="red")
                )
                logger.error("Failed to set status to offline")
            else:
                logger.debug("Status set to offline successfully")

        await client.disconnect()
        logger.info("Client session closed")

    except SessionNotFoundError as e:
        app.console.print(
            "Session not found:",
            app.config.telegram.session,
            style=Style(color="red"),
        )
        logger.error(f"Session not found: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise
