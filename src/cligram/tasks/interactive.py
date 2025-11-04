import asyncio
import logging
from typing import Optional

from rich import get_console
from telethon import TelegramClient, events, functions, hints
from telethon.tl.types import Message

from .. import Application, utils
from . import telegram

logger = None


def setup_logger():
    global logger
    logger = logging.getLogger("cligram.tasks.interactive")


async def main(
    app: Application,
    shutdown_event: asyncio.Event,
):
    """Interactive task."""
    setup_logger()

    app.status.update("Starting interactive session...")
    await telegram.setup(
        app=app, shutdown_event=shutdown_event, callback=interactive_callback
    )


async def interactive_callback(
    app: Application, shutdown_event: asyncio.Event, client: TelegramClient
):
    """Callback for interactive task."""
    app.status.stop()
    app.console.print("[green]Interactive session started![/green]")

    @client.on(events.NewMessage)
    async def handler(event: events.NewMessage.Event):
        msg: Message = event.message
        user = await client.get_entity(msg.peer_id)
        logger.info(f"From {user.id}\n{msg.message}")
        print_event(event="New Message", entity=user, text=msg.message)

        # mark message as read
        await client(
            functions.messages.ReadHistoryRequest(peer=msg.peer_id, max_id=msg.id)
        )

    # Wait for shutdown event
    await shutdown_event.wait()

    # Remove event handler
    client.remove_event_handler(handler)

    app.status.start()


def print_event(event: str, entity: hints.Entity, text: Optional[str] = None):
    """Print a Telegram event."""
    entity_name = utils.get_entity_name(entity)

    console = get_console()
    console.print(
        f"[bold blue]{event}[/bold blue] from [bold green]{entity_name}[/bold green] (ID: {entity.id})"
    )
    if text:
        console.print(text)
