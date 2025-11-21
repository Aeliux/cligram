import argparse
import asyncio
import logging
import shlex
import sys
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from typing import TYPE_CHECKING, Any, Awaitable, Callable, List, Optional

from rich.control import Control, ControlType  # type: ignore
from rich.table import Table
from telethon import TelegramClient, events, functions, hints
from telethon.tl.types import Channel, Message, TypeInputPeer, User, Username

from .. import InteractiveMode, utils
from . import telegram

if TYPE_CHECKING:
    from .. import Application

logger: logging.Logger = logging.getLogger(__name__)


class InputHandler:
    """Handle async input without blocking output or breaking mid-type input."""

    def __init__(self, context: "Context"):
        self.context = context
        self.input_lock = asyncio.Lock()
        self.input_queue: asyncio.Queue[str] = asyncio.Queue()

        self._prompt_text: str | None = None

    def print_prompt(self):
        """Print the input prompt."""
        prefix = self._prompt_text or ""
        self.context.console.print(f"{prefix}> ", end="", highlight=False)

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
            self.context.console.control(Control(ControlType.CARRIAGE_RETURN))
            self.context.console.print(" " * self.context.console.width, end="")
            self.context.console.control(Control(ControlType.CARRIAGE_RETURN))

            # Print the message
            self.context.console.print(*args, **kwargs)


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

    def __init__(self, context: "Context"):
        self.context = context
        self.selected_entity: Optional[TypeInputPeer] = None
        self.commands: dict[str, Command] = {}

        self._add_select()
        self._add_resolve()
        self._add_send()

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

    def _add_send(self):
        sendParser = argparse.ArgumentParser(
            prog="send",
            description="Send a message to the selected entity",
            exit_on_error=False,
        )
        sendParser.add_argument(
            "message",
            type=str,
            help="The message text to send",
        )

        sendParser.add_argument(
            "-e",
            "--entity",
            default=None,
            type=str,
            help="Username or ID of the entity to send the message to, if not provided, will use the selected entity",
        )

        self.add_command(
            Command(
                name="send",
                aliases=[],
                description="Send a message to the selected entity",
                parser=sendParser,
                handler=self.cmd_send,
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
        parts = shlex.split(command)
        cmd = parts[0]

        if cmd == "help":
            self.context.console.print("[bold]Available Commands:[/bold]")
            table = Table.grid(padding=(0, 5))
            table.add_column("Command")
            table.add_column("Description")

            for command_obj in self.commands.values():
                table.add_row(
                    f"[bold]{command_obj.name}[/bold]", command_obj.description
                )
            self.context.console.print(table)
            self.context.console.print(
                "\nType <command> --help for more details on a command."
            )
        elif cmd in self.commands:
            command_obj = self.commands[cmd]
            try:
                parsed = command_obj.parser.parse_args(parts[1:])
            except argparse.ArgumentError as e:
                self.context.console.print(f"[red]Argument error:[/red] {e}")
                return
            except SystemExit:
                return
            await command_obj.handler(self, parsed)
        else:
            self.context.console.print(f"[dim]Unknown command: {command}[/dim]")

    async def get_input_entity(self, query: str | int | None):
        """Get input entity from query or selected entity."""
        if query is None:
            if self.selected_entity is None:
                raise ValueError("No entity selected.")
            return self.selected_entity

        try:
            query = int(query)
        except ValueError:
            pass

        return await self.context.client.get_input_entity(query)

    async def cmd_select(self, _, args: argparse.Namespace):
        """Handler for select command."""
        if not isinstance(args, argparse.Namespace):
            self.context.console.print(
                "[red]Invalid arguments for select command.[/red]"
            )
            return

        if args.clear:
            self.selected_entity = None
            self.context.set_prompt(source=InteractiveMode.CLIGRAM, prompt=None)
            self.context.console.print("[green]Selection cleared.[/green]")
            return

        entity_query = args.entity
        if not entity_query:
            self.context.console.print("[red]No entity provided to select.[/red]")
            return

        try:
            ientity = await self.get_input_entity(entity_query)
            id = utils.telegram.get_id_from_input_peer(ientity)
            if id is None:
                raise ValueError("Could not determine entity ID.")
            self.selected_entity = ientity
            self.context.set_prompt(source=InteractiveMode.CLIGRAM, prompt=str(id))
            self.context.console.print(
                f"[green]Entity selected:[/green] {type(ientity).__name__}:{id}"
            )
        except Exception as e:
            self.context.console.print(f"[red]Error selecting entity:[/red] {e}")

    async def cmd_resolve(self, _, args: argparse.Namespace):
        """Handler for resolve command."""
        if not isinstance(args, argparse.Namespace):
            self.context.console.print(
                "[red]Invalid arguments for resolve command.[/red]"
            )
            return

        entity_name = args.entity
        extend = args.all

        try:
            ientity = await self.get_input_entity(entity_name)
            entity = await self.context.client.get_entity(ientity)
            if isinstance(entity, list):
                entity = entity[0]
            self.context.console.print(f"[green]Entity resolved:[/green] {entity.id}")
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
            usernames: List[Username] = getattr(entity, "usernames", [])
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
            self.context.console.print(table)

        except Exception as e:
            self.context.console.print(f"[red]Error resolving entity:[/red] {e}")

    async def cmd_send(self, _, args: argparse.Namespace):
        """Handler for send command."""
        if not isinstance(args, argparse.Namespace):
            self.context.console.print("[red]Invalid arguments for send command.[/red]")
            return

        entity_query = args.entity
        message_text = args.message

        try:
            ientity = await self.get_input_entity(entity_query)
            id = utils.telegram.get_id_from_input_peer(ientity)
            await self.context.client.send_message(ientity, message_text)
            self.context.console.print(f"[green]Message sent to {id}.[/green]")
        except Exception as e:
            self.context.console.print(f"[red]Error sending message:[/red] {e}")


class PythonExecutor:
    """Execute Python code in the interactive session context."""

    def __init__(self, context: "Context"):
        self.context = context
        self.result_history: list[Any] = []
        self.max_history = 100
        self._pending_tasks: dict[int, TaskAwaiter] = {}
        self._task_counter = 0
        self.locals: dict[str, Any] = {
            "__context__": self.context,
            "_": None,  # Last result
            "__results__": self.result_history,  # All results
            "a": self._await_helper,  # Helper to await coroutines
            "__tasks__": self._pending_tasks,  # Pending tasks
        }
        self.globals: dict[str, Any] = {}

    def _get_result(self, index: int = -1):
        """Get result from history by index (default: last result)."""
        if not self.result_history:
            return None
        try:
            return self.result_history[index]
        except IndexError:
            return None

    def _store_result(self, result):
        """Store result in history and update quick access variable."""
        if result is not None:
            self.result_history.append(result)
            if len(self.result_history) > self.max_history:
                self.result_history.pop(0)

            self.locals["_"] = result

    def _await_helper(self, coro):
        """Helper function to await a coroutine and get its result.
        Creates a task and returns a TaskAwaiter object that can be used to get the result.

        Usage:
            task = a(client.get_me())
            # Later...
            task.result()  # Get result when done
            task.done()    # Check if done
        """
        if not asyncio.iscoroutine(coro):
            raise TypeError(f"a() requires a coroutine, got {type(coro).__name__}")

        task_id = self._task_counter
        self._task_counter += 1

        task = asyncio.create_task(coro)
        awaiter = TaskAwaiter(task, task_id)
        self._pending_tasks[task_id] = awaiter

        # Clean up when done
        def cleanup(t):
            # Keep in dict for access, but mark as done
            pass

        task.add_done_callback(cleanup)
        return awaiter

    async def execute(self, code: str) -> tuple[bool, str]:
        """Execute Python code and return (success, output).

        Args:
            code: Python code to execute

        Returns:
            Tuple of (success: bool, output: str)
        """
        stdout_capture = StringIO()
        stderr_capture = StringIO()

        try:
            # Check if this is an expression or statement
            try:
                compile(code, "<interactive>", "eval")
                is_expression = True
            except SyntaxError:
                is_expression = False

            result = None
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                if is_expression:
                    # Evaluate expression and print result
                    result = eval(code, self.globals, self.locals)  # nosec

                    # Handle awaitable results
                    if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                        result = await result

                    # Store the result
                    self._store_result(result)

                    if result is not None:
                        print(repr(result))
                else:
                    # Execute statement
                    compiled = compile(code, "<interactive>", "exec")
                    exec(compiled, self.globals, self.locals)  # nosec

            output = stdout_capture.getvalue()
            errors = stderr_capture.getvalue()

            full_output = ""
            if output:
                full_output += output
            if errors:
                full_output += errors

            return True, full_output.rstrip() if full_output else ""

        except Exception as e:
            error_output = stderr_capture.getvalue()
            if error_output:
                error_output += "\n"
            error_output += "".join(
                traceback.format_exception(type(e), e, e.__traceback__)
            )
            return False, error_output.rstrip()

    async def execute_and_print(self, code: str):
        """Execute code and print the result to console."""
        success, output = await self.execute(code)

        if output:
            await self.context.input_handler.safe_print(output)
        elif not success:
            await self.context.input_handler.safe_print(
                "[red]Execution failed with no output[/red]"
            )

    def add_variable(self, name: str, value):
        """Add a variable to the executor's local scope."""
        self.locals[name] = value

    def get_variable(self, name: str):
        """Get a variable from the executor's local scope."""
        return self.locals.get(name)

    def list_variables(self) -> dict:
        """Get all variables in the executor's local scope."""
        return {k: v for k, v in self.locals.items() if not k.startswith("_")}

    def clear_history(self):
        """Clear result history."""
        self.result_history.clear()
        self.locals["_"] = None


class TaskAwaiter:
    """Wrapper for async tasks to allow easy result access."""

    def __init__(self, task: asyncio.Task, task_id: int):
        self.task = task
        self.task_id = task_id

    def done(self) -> bool:
        """Check if the task is done."""
        return self.task.done()

    def result(self):
        """Get the result of the task. Blocks if not done yet.

        Returns:
            The result of the coroutine

        Raises:
            asyncio.TimeoutError: If timeout is reached
            Exception: Any exception raised by the coroutine
        """
        while not self.task.done():
            time.sleep(0.1)

        return self.task.result()

    def exception(self):
        """Get the exception raised by the task, if any."""
        if not self.task.done():
            return None
        return self.task.exception()

    def cancel(self):
        """Cancel the task."""
        return self.task.cancel()

    def __repr__(self):
        status = "done" if self.task.done() else "pending"
        return f"<TaskAwaiter {self.task_id} ({status})>"

    def __await__(self):
        """Allow awaiting the TaskAwaiter directly."""
        return self.task.__await__()


def _tryattr(obj, attr: str):
    value = getattr(obj, attr, None)
    return str(value) if value is not None else "N/A"


class Context:
    """Context for interactive session."""

    @property
    def mode(self) -> InteractiveMode:
        """Get the current interactive mode."""
        return self._mode

    @property
    def print_announcements(self) -> bool:
        """Whether to print announcements."""
        return self._print_announcements

    def __init__(self, app: "Application", client: TelegramClient):
        self.app = app
        self.console = app.console
        self.client = client

        self.input_handler = InputHandler(self)
        self.command_handler = CommandHandler(self)
        self.executor = PythonExecutor(self)

        self._mode: InteractiveMode = None  # type: ignore
        self._available_modes = list(InteractiveMode)
        self._input_processor_task: Optional[asyncio.Task] = None
        self._print_announcements: bool = True
        self._cmd_prompt: str | None = None
        self._missed_announcements: asyncio.Queue = asyncio.Queue()

    async def start(self):
        """Start the interactive session."""
        await self.input_handler.start()
        self._input_processor_task = asyncio.create_task(self._process_input())

        self.console.print("[green]Interactive session started![/green]")
        self.console.print("[dim]Type ! to toggle modes, CTRL+C to exit[/dim]")

        await self.set_mode(self.app.config.interactive.mode)

    async def stop(self):
        """Stop the interactive session."""
        if self._input_processor_task:
            self._input_processor_task.cancel()
            try:
                await self._input_processor_task
            except asyncio.CancelledError:
                pass

        self.console.print("[green]Interactive session ended[/green]")

    def set_prompt(self, source: InteractiveMode, prompt: str | None):
        """Set the input prompt for the given interactive mode."""
        if source == InteractiveMode.CLIGRAM:
            self._cmd_prompt = prompt

        self._update_prompt()

    def _update_prompt(self):
        if self._mode == InteractiveMode.CLIGRAM:
            self.input_handler._prompt_text = self._cmd_prompt
        elif self._mode == InteractiveMode.PYTHON:
            self.input_handler._prompt_text = "python"

    async def set_mode(self, mode: InteractiveMode):
        """Set the interactive mode."""
        self._mode = mode

        if self._mode == InteractiveMode.CLIGRAM:
            self.console.print("[dim]Command mode, type help for commands[/dim]")
            await self.set_print_announcements(True)
        elif self._mode == InteractiveMode.PYTHON:
            self.console.print("[dim]Python executor mode[/dim]")
            await self.set_print_announcements(False)

        self._update_prompt()

    async def set_print_announcements(self, value: bool):
        """Enable or disable printing announcements."""
        if value == self._print_announcements:
            return
        self._print_announcements = value

        if self._print_announcements:
            self.console.print(
                "[green]Updates announcements enabled, missed announcements will be flushed[/green]"
            )
            await self.flush_missed_announcements()
        else:
            self.console.print(
                "[yellow]Updates announcements disabled, updates still logged[/yellow]"
            )

    async def announce(
        self,
        message: str,
    ):
        """Announce a message to the user, if announcements are enabled.
        Otherwise, queue the message for later.

        Args:
            message: The message to announce.
        """
        if not self.print_announcements:
            await self._missed_announcements.put(message)
            return

        await self.input_handler.safe_print(message)

        self.input_handler.print_prompt()

    async def flush_missed_announcements(self):
        """Flush all missed announcements.

        Raises:
            RuntimeError: If announcements are disabled.
        """
        if not self.print_announcements:
            raise RuntimeError("Updates announcements are disabled.")

        while not self._missed_announcements.empty():
            message = await self._missed_announcements.get()
            await self.announce(message)

    async def announce_event(
        self,
        event: str,
        entity: hints.Entity,
        text: Optional[str] = None,
    ):
        """Announce an event from a Telegram entity.

        Args:
            event: The event name.
            entity: The Telegram entity involved in the event.
            text: Optional additional text to include in the announcement.
        """
        entity_name = utils.get_entity_name(entity)
        formatted_event_message = (
            f"[bold blue]{event}[/bold blue] from [bold green]{entity_name}[/bold green] (ID: {entity.id})"
            + (f"\n{text}" if text else "")
        )

        logger.info(
            f"event '{event}' from {entity_name} (ID: {entity.id})"
            + (f"\n{text}" if text else "")
        )

        await self.announce(formatted_event_message)

    async def _process_input(self):
        self.input_handler.print_prompt()
        while not self.app.shutdown_event.is_set():
            try:
                line = await asyncio.wait_for(
                    self.input_handler.read_input(), timeout=1.0
                )

                if not line.strip():
                    continue

                sline = line.strip()

                if sline == "!":
                    current_index = self._available_modes.index(self._mode)
                    next_index = (current_index + 1) % len(self._available_modes)
                    await self.set_mode(self._available_modes[next_index])
                elif self.mode == InteractiveMode.PYTHON:
                    await self.executor.execute_and_print(sline)
                elif self.mode == InteractiveMode.CLIGRAM:
                    await self.command_handler.handle_command(sline)

                # Print new prompt after command is handled
                self.input_handler.print_prompt()

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.console.print(f"[red]Error processing input:[/red] {e}")
                logger.error(f"Error processing input: {e}")


async def main(app: "Application"):
    """Interactive task."""
    app.status.update("Starting interactive session...")
    await telegram.setup(app=app, callback=interactive_callback)


async def interactive_callback(app: "Application", client: TelegramClient):
    """Callback for interactive task."""
    app.status.stop()

    context = Context(app, client)
    await context.start()

    @client.on(events.NewMessage)  # type: ignore
    async def handler(event: events.NewMessage.Event):
        msg: Message = event.message
        entity = await client.get_entity(msg.peer_id)
        if isinstance(entity, list):
            entity = entity[0]

        await context.announce_event(
            event="New Message",
            entity=entity,
            text=msg.message,
        )

        # mark message as read
        await client(
            functions.messages.ReadHistoryRequest(
                peer=msg.peer_id,
                max_id=msg.id,  # type: ignore
            )
        )

    # Wait for shutdown event
    await app.shutdown_event.wait()

    await context.stop()

    # Remove event handler
    client.remove_event_handler(handler)

    app.status.start()
