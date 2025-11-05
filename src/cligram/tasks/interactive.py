import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional

from rich.console import Console
from rich.control import Control, ControlType
from rich.table import Table
from telethon import TelegramClient, events, functions, hints
from telethon.tl.types import Channel, Chat, Message, TypeInputPeer, User, Username

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
        self.input_lock = asyncio.Lock()
        self.input_queue = asyncio.Queue()

        self.prompt_text = None

    def print_prompt(self):
        """Print the input prompt."""
        prefix = self.prompt_text or ""
        self.console.print(f"{prefix}> ", end="", highlight=False)

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

    async def safe_print(self, *args, **kwargs):
        """Print output while preserving input prompt."""
        async with self.input_lock:
            # Clear current line
            self.console.control(Control(ControlType.CARRIAGE_RETURN))
            self.console.print(" " * self.console.width, end="")
            self.console.control(Control(ControlType.CARRIAGE_RETURN))

            # Print the message
            self.console.print(*args, **kwargs)


@dataclass
class Command:
    name: str
    """The name of the command."""

    aliases: List[str]
    """The list of aliases for the command."""

    description: str
    """The description of the command."""

    parser: argparse.ArgumentParser
    """The argument parser for the command."""

    handler: Callable[["CommandHandler", argparse.Namespace], Awaitable[None]]
    """The function that handles the command."""


class CommandHandler:
    """Handle user commands in interactive mode."""

    def __init__(
        self, app: Application, input_handler: InputHandler, client: TelegramClient
    ):
        self.app = app
        self.input_handler = input_handler
        self.client = client
        self.selected_entity: Optional[TypeInputPeer] = None
        self.commands: dict[str, Command] = {}

        self._add_select()
        self._add_resolve()

    def _add_select(self):
        selectParser = argparse.ArgumentParser(
            prog="select", description="Select a Telegram entity", exit_on_error=False
        )
        selectParser.add_argument(
            "entity",
            nargs="?",
            default=None,
            type=str,
            help="Username or ID of the entity to select",
        )
        selectParser.add_argument(
            "-c", "--clear", action="store_true", help="Clear the current selection"
        )

        self.add_command(
            Command(
                name="select",
                aliases=[],
                description="Select a Telegram entity by username or ID",
                parser=selectParser,
                handler=self.cmd_select,
            )
        )

    def _add_resolve(self):
        resolveParser = argparse.ArgumentParser(
            prog="resolve", description="Resolve a Telegram entity", exit_on_error=False
        )
        resolveParser.add_argument(
            "-e",
            "--entity",
            default=None,
            type=str,
            help="Username or ID of the entity to resolve, if not provided, will use the selected entity",
        )
        resolveParser.add_argument(
            "-a", "--all", action="store_true", help="Show full data of the entity"
        )

        self.add_command(
            Command(
                name="resolve",
                aliases=[],
                description="Resolve a Telegram entity by username or ID",
                parser=resolveParser,
                handler=self.cmd_resolve,
            )
        )

    def add_command(self, command: Command):
        """Add a new command."""
        if command.name in self.commands:
            raise ValueError(f"Command {command.name} already exists.")

        if not isinstance(command.parser, argparse.ArgumentParser):
            raise TypeError(
                "Command parser must be an instance of argparse.ArgumentParser."
            )

        if command.parser.exit_on_error:
            raise ValueError("Command parser must not exit on error.")

        if not callable(command.handler):
            raise TypeError("Command handler must be callable.")

        if not asyncio.iscoroutinefunction(command.handler):
            raise TypeError("Command handler must be an async function.")

        self.commands[command.name] = command

    async def handle_command(self, command: str):
        """Handle user commands."""
        parts = command.split(" ")
        cmd = parts[0]

        if cmd == "help":
            self.app.console.print("[bold]Available Commands:[/bold]")
            table = Table.grid(padding=(0, 5))
            table.add_column("Command")
            table.add_column("Description")

            for command in self.commands.values():
                table.add_row(f"[bold]{command.name}[/bold]", command.description)
            self.app.console.print(table)
            self.app.console.print()
            self.app.console.print(
                "\nType <command> --help for more details on a command."
            )
        elif cmd in self.commands:
            command_obj = self.commands[cmd]
            try:
                parsed = command_obj.parser.parse_args(parts[1:])
            except argparse.ArgumentError as e:
                self.app.console.print(f"[red]Argument error:[/red] {e}")
                return
            except SystemExit:
                return
            await command_obj.handler(self, parsed)
        else:
            self.app.console.print(f"[dim]Unknown command: {command}[/dim]")

    async def get_input_entity(self, query: str | None):
        """Get input entity from query or selected entity."""
        if query is None:
            if self.selected_entity is None:
                raise ValueError("No entity selected.")
            return self.selected_entity

        try:
            query = int(query)
        except ValueError:
            pass

        return await self.client.get_input_entity(query)

    async def cmd_select(self, _, args: argparse.Namespace):
        """Handler for select command."""
        if not isinstance(args, argparse.Namespace):
            self.app.console.print("[red]Invalid arguments for select command.[/red]")
            return

        if args.clear:
            self.selected_entity = None
            self.input_handler.prompt_text = None
            self.app.console.print("[green]Selection cleared.[/green]")
            return

        entity_query = args.entity
        if not entity_query:
            self.app.console.print("[red]No entity provided to select.[/red]")
            return

        try:
            entity = await self.get_input_entity(entity_query)
            id = (
                getattr(entity, "user_id", None)
                or getattr(entity, "channel_id", None)
                or getattr(entity, "chat_id", None)
            )
            if id is None:
                raise ValueError("Could not determine entity ID.")
            self.selected_entity = entity
            self.input_handler.prompt_text = str(id)
            self.app.console.print(
                f"[green]Entity selected:[/green] {type(entity).__name__}:{id}"
            )
        except Exception as e:
            self.app.console.print(f"[red]Error selecting entity:[/red] {e}")

    async def cmd_resolve(self, _, args: argparse.Namespace):
        """Handler for resolve command."""
        if not isinstance(args, argparse.Namespace):
            self.app.console.print("[red]Invalid arguments for resolve command.[/red]")
            return

        entity_name = args.entity
        extend = args.all

        try:
            ientity = await self.get_input_entity(entity_name)
            entity = await self.client.get_entity(ientity)
            self.app.console.print(f"[green]Entity resolved:[/green] {entity.id}")
            table = Table.grid(padding=(0, 5))
            table.add_column("Field")
            table.add_column("Value")

            bot = isinstance(entity, User) and getattr(entity, "bot", False)
            group = isinstance(entity, Channel) and (
                getattr(entity, "megagroup", False)
                or getattr(entity, "gigagroup", False)
            )

            # Show additional info about this entity
            table.add_row("Type", entity.__class__.__name__)
            if isinstance(entity, User):
                table.add_row("Is Bot", str(bot))
            elif isinstance(entity, Channel):
                table.add_row("Is Group", str(group))
            table.add_row("Name", utils.get_entity_name(entity))
            table.add_row(
                "Has Profile Photo", str(utils.telegram.has_profile_photo(entity))
            )

            username = getattr(entity, "username", None)
            usernames: List[Username] = getattr(entity, "usernames", None)
            if username:
                table.add_row("Username", username)
            elif usernames:
                table.add_row("Usernames", "\n".join([u.username for u in usernames]))
            if isinstance(entity, User) and not bot:
                table.add_row("Phone", _tryattr(entity, "phone"))
                table.add_row("Status", utils.get_status(entity))
            if bot:
                table.add_row("Bot Users", _tryattr(entity, "bot_active_users"))
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

    command_handler = CommandHandler(app, input_handler, client)

    # Input processing loop
    async def process_input():
        input_handler.print_prompt()
        while not shutdown_event.is_set():
            try:
                line = await asyncio.wait_for(input_handler.read_input(), timeout=1.0)

                if line.strip():
                    await command_handler.handle_command(line.strip())

                # Print new prompt after command is handled
                input_handler.print_prompt()

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

    await input_handler.safe_print(
        f"[bold blue]{event}[/bold blue] from [bold green]{entity_name}[/bold green] (ID: {entity.id})"
    )
    if text:
        await input_handler.safe_print(text)

    input_handler.print_prompt()
