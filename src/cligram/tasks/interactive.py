import asyncio
import logging
import sys
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional

from rich.console import Console
from rich.table import Table
from telethon import TelegramClient, events, functions, hints
from telethon.tl.types import Channel, Chat, Message, User, Username

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


@dataclass
class Command:
    name: str
    """The name of the command."""

    description: str
    """The description of the command."""

    handler: Callable[["CommandHandler", List[str]], Awaitable[None]]
    """The function that handles the command."""


class CommandHandler:
    """Handle user commands in interactive mode."""

    def __init__(self, app: Application, client: TelegramClient):
        self.app = app
        self.client = client
        self.commands: dict[str, Command] = {}

        self.commands["resolve"] = Command(
            name="resolve",
            description="Resolve a Telegram entity by username or ID, with optional flags -a/--all for full data",
            handler=self.cmd_resolve,
        )

    async def handle_command(self, command: str):
        """Handle user commands."""
        parts = command.split(" ")
        cmd = parts[0]
        args = parts[1:]
        if cmd == "help":
            self.app.console.print("[bold]Available Commands:[/bold]")
            table = Table.grid(padding=(0, 5))
            table.add_column("Command")
            table.add_column("Description")

            for command in self.commands.values():
                table.add_row(f"[bold]{command.name}[/bold]", command.description)
            self.app.console.print(table)
        elif cmd in self.commands:
            command_obj = self.commands[cmd]
            await command_obj.handler(self, args)
        else:
            self.app.console.print(f"[dim]Unknown command: {command}[/dim]")

    async def get_entity(self, entity: hints.EntitiesLike):
        """Get entity."""
        entity: hints.Entity = await self.client.get_entity(entity)
        return entity

    async def cmd_resolve(self, _, args: List[str]):
        """Handler for resolve command."""
        if not args:
            self.app.console.print("[red]Usage: resolve <entity_name>[/red]")
            return

        # detect and remove flags from args
        flags = [arg for arg in args if arg.startswith("-")]
        args = [arg for arg in args if not arg.startswith("-")]

        extend = "-a" in flags or "--all" in flags

        entity_name = args[0]
        try:
            entity = await self.get_entity(entity_name)
            self.app.console.print(f"[green]Entity resolved:[/green] {entity.id}")
            table = Table.grid(padding=(0, 5))
            table.add_column("Field")
            table.add_column("Value")

            # Show additional info about this entity
            table.add_row("Type", entity.__class__.__name__)
            table.add_row("Name", utils.get_entity_name(entity))
            table.add_row("Has Profile Photo", utils.telegram.has_profile_photo(entity))

            username = getattr(entity, "username", None)
            usernames: List[Username] = getattr(entity, "usernames", None)
            if username:
                table.add_row("Username", username)
            elif usernames:
                table.add_row("Usernames", "\n".join([u.username for u in usernames]))
            if isinstance(entity, User):
                table.add_row("Phone", _tryattr(entity, "phone"))
                table.add_row("Status", utils.get_status(entity))
                table.add_row("Is Bot", _tryattr(entity, "bot"))
            table.add_row("Is Verified", _tryattr(entity, "verified"))
            table.add_row("Is Scam", _tryattr(entity, "scam"))
            table.add_row("Is Restricted", _tryattr(entity, "restricted"))
            if extend:
                table.add_row("Full Data", entity.stringify())
            self.app.console.print(table)

        except Exception as e:
            self.app.console.print(f"[red]Error resolving entity:[/red] {e}")


def _tryattr(obj, attr: str):
    value = getattr(obj, attr, None)
    return str(value) if value is not None else "N/A"


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
    app.console.print("[dim]Type help for commands, CTRL+C to exit[/dim]")

    input_handler = InputHandler(app.console)
    await input_handler.start()

    command_handler = CommandHandler(app, client)

    # Input processing loop
    async def process_input():
        app.console.print("> ", end="", highlight=False)
        while not shutdown_event.is_set():
            try:
                line = await asyncio.wait_for(input_handler.read_input(), timeout=1.0)
                input_handler.current_input = ""

                if line.strip():
                    await command_handler.handle_command(line.strip())

                # Print new prompt after command is handled
                app.console.print("> ", end="", highlight=False)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                app.console.print(f"[red]Error processing input:[/red] {e}")
                logger.error(f"Error processing input: {e}")

    # Start input processing
    input_task = asyncio.create_task(process_input())

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
