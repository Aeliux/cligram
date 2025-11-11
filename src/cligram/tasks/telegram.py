import logging
from typing import TYPE_CHECKING, Callable, Coroutine, Optional

from rich.style import Style
from telethon import TelegramClient
from telethon.tl import functions
from telethon.tl.types import User

from .. import exceptions, utils

if TYPE_CHECKING:
    from .. import Application, CustomSession, Proxy

logger: logging.Logger = None  # type: ignore


def setup_logger():
    global logger
    logger = logging.getLogger("cligram.tasks.telegram")


async def setup(
    app: "Application",
    callback: Callable[["Application", TelegramClient], Coroutine],
    session: Optional["CustomSession"] = None,
    proxy: Optional["Proxy"] = None,
    disconnect_expected: bool = False,
):
    """Setup Telegram client."""
    setup_logger()

    try:
        session = session or utils.get_session(app.config)

        if not proxy:
            proxy = await _setup_connection(app)
        _finalize_connection(app, proxy)

        client = await _init_client(app=app, session=session, proxy=proxy)

        try:
            app.check_shutdown()
            await _fetch_account_info(app, client)

            if app.config.telegram.startup.count_unread_messages:
                await _check_unread_messages(app, client)

            await callback(app, client)
        finally:
            app.status.update("Shutting down client...")
            if not client.is_connected():
                if disconnect_expected:
                    logger.info("Client disconnected as expected")
                else:
                    logger.warning("Client disconnected unexpectedly")
                    app.console.print(
                        "Client disconnected unexpectedly", style=Style(color="yellow")
                    )
                return

            await client(functions.account.UpdateStatusRequest(offline=True))

            await client.disconnect()  # type: ignore
            logger.info("Client session closed")

    except exceptions.SessionNotFoundError as e:
        app.console.print(
            "Session not found:",
            app.config.telegram.session,
            style=Style(color="red"),
        )
        logger.error(f"Session not found: {e}")
    except exceptions.NoWorkingConnectionError as e:
        app.console.print("No working connection available", style=Style(color="red"))
        logger.error(f"No working connection available: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise


async def _setup_connection(app: "Application") -> "Proxy | None":
    from .. import ProxyManager

    app.status.update("Testing connections...")
    logger.info("Testing connections")
    proxy_manager = ProxyManager.from_config(app.config)
    await proxy_manager.test_proxies(shutdown_event=app.shutdown_event, oneshot=True)
    app.check_shutdown()
    return proxy_manager.current_proxy


def _finalize_connection(app, proxy):
    if utils.validate_proxy(proxy):
        if proxy.is_direct:
            logger.info("Using direct connection")
        else:
            app.console.print(
                f"Using {proxy.type.value} proxy: {proxy.host}:{proxy.port}"
            )
            logger.info(f"Using proxy: [{proxy.type.name}] {proxy.host}:{proxy.port}")
    else:
        logger.error("No working connection available, aborting")
        raise exceptions.NoWorkingConnectionError("No working connection available")


async def _check_unread_messages(app, client):
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


async def _fetch_account_info(app, client):
    app.status.update("Fetching account information...")
    logger.debug("Fetching account information")
    me: User = await client.get_me()

    if me.first_name and me.last_name:
        name = f"{me.first_name} {me.last_name}"
    else:
        name = me.first_name

    await client(functions.account.UpdateStatusRequest(offline=False))

    app.console.print(f"Logged in as {name} (ID: {me.id})")
    logger.info(f"Logged in as {name} (ID: {me.id})")

    if app.config.app.verbose:
        logger.debug(f"Account ID: {me.id}")
        logger.debug(f"Full Name: {name}")
        logger.debug(f"Username: {me.username}")
        logger.debug(f"Phone: {me.phone}")


async def _init_client(
    app: "Application",
    session: "CustomSession",
    proxy: Optional["Proxy"] = None,
) -> TelegramClient:
    """Initialize Telegram client."""
    app.status.update("Initializing client...")

    client: TelegramClient = utils.get_client(
        config=app.config, device=app.device, proxy=proxy, session=session
    )

    app.status.update("Logging in...")
    logger.info(f"Logging in with {client.session.filename} session")  # type: ignore

    def _phone_callback():
        app.status.stop()
        return input("Please enter your phone (or bot token): ")

    await client.start(phone=_phone_callback)  # type: ignore
    app.status.start()
    return client
