import asyncio
import logging
import sys
from typing import Optional

from rich import get_console
from rich.console import Console
from telethon import TelegramClient, events, functions, hints
from telethon.tl.types import Message

from .. import Application, utils
from . import telegram

logger = None


def setup_logger():
    global logger
    logger = logging.getLogger("cligram.tasks.interactive")


class InputHandler:
    """Handle async input without blocking output or breaking mid-type input."""

    def __init__(self, console: Console):
        self.console = console
        self.current_input = ""
        self.input_lock = asyncio.Lock()
        self.input_queue = asyncio.Queue()

    async def read_input(self) -> str:
        """Read a line of input asynchronously."""
        return await self.input_queue.get()

    async def start(self):
        """Start the input reader task."""
        asyncio.create_task(self._input_reader())

    async def _input_reader(self):
        """Background task to read stdin."""
        loop = asyncio.get_event_loop()
        while True:
            try:
                # Read input in executor to avoid blocking
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    break
                await self.input_queue.put(line.rstrip("\n"))
            except Exception as e:
                logger.error(f"Error reading input: {e}")
                break

    async def print_with_prompt(self, *args, **kwargs):
        """Print output while preserving input prompt."""
        async with self.input_lock:
            # Clear current line if there's input
            if self.current_input:
                self.console.print("\r" + " " * (len(self.current_input) + 2), end="")
                self.console.print("\r", end="")

            # Print the message
            self.console.print(*args, **kwargs)

            # Restore prompt and input
            if self.current_input:
                self.console.print(f"> {self.current_input}", end="", highlight=False)


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
    app.console.print("[dim]Type help for commands, quit to exit[/dim]")

    input_handler = InputHandler(app.console)
    await input_handler.start()

    @client.on(events.NewMessage)
    async def handler(event: events.NewMessage.Event):
        msg: Message = event.message
        user = await client.get_entity(msg.peer_id)
        logger.info(f"From {user.id}\n{msg.message}")

        await print_event(
            input_handler=input_handler,
            event="New Message",
            entity=user,
            text=msg.message,
        )

        # mark message as read
        await client(
            functions.messages.ReadHistoryRequest(peer=msg.peer_id, max_id=msg.id)
        )

    # Input processing loop
    async def process_input():
        app.console.print("> ", end="", highlight=False)
        while not shutdown_event.is_set():
            try:
                line = await asyncio.wait_for(input_handler.read_input(), timeout=1.0)
                input_handler.current_input = ""

                if line.strip():
                    await handle_command(app, client, line.strip())

                # Print new prompt after command is handled
                app.console.print("> ", end="", highlight=False)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing input: {e}")

    # Start input processing
    input_task = asyncio.create_task(process_input())

    # Wait for shutdown event
    await shutdown_event.wait()

    # Cleanup
    input_task.cancel()
    try:
        await input_task
    except asyncio.CancelledError:
        pass

    # Remove event handler
    client.remove_event_handler(handler)

    app.status.start()


async def handle_command(app: Application, client: TelegramClient, command: str):
    """Handle user commands."""
    if command == "quit":
        app.console.print("[yellow]Shutting down...[/yellow]")
        app.shutdown_event.set()
    elif command == "help":
        app.console.print("[bold]Available commands:[/bold]")
        app.console.print("  help  - Show this help message")
        app.console.print("  quit  - Exit the application")
    else:
        app.console.print(f"[dim]Unknown command: {command}[/dim]")


async def print_event(
    input_handler: InputHandler,
    event: str,
    entity: hints.Entity,
    text: Optional[str] = None,
):
    """Print a Telegram event without breaking user input."""
    entity_name = utils.get_entity_name(entity)

    await input_handler.print_with_prompt(
        f"[bold blue]{event}[/bold blue] from [bold green]{entity_name}[/bold green] (ID: {entity.id})"
    )
    if text:
        await input_handler.print_with_prompt(text)
