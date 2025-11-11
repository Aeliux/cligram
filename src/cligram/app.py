import asyncio
import logging
import platform
import signal
import sys
from typing import TYPE_CHECKING, Callable, Coroutine, Optional

from rich import get_console
from rich.status import Status

from . import StateManager, exceptions, utils

if TYPE_CHECKING:
    from . import Config

logger: logging.Logger = logging.getLogger(__name__)
app_instance: Optional["Application"] = None
_recv_signals: int = 0


def get_app() -> "Application":
    """
    Retrieve the global running application instance.

    Returns:
        Application: The global application instance

    Raises:
        ApplicationNotRunningError: If there is no running application
    """
    global app_instance
    if app_instance is None:
        raise exceptions.ApplicationNotRunningError("There is no running application")
    return app_instance


class Application:
    def __init__(self, config: "Config"):
        self.config = config
        """Application configuration."""

        self.device: utils.DeviceInfo = utils.get_device_info()
        """Information about the current device/environment."""

        self.state = StateManager(data_dir=self.config.data_path)
        """"State manager for application state persistence."""

        self.shutdown_event: asyncio.Event = asyncio.Event()
        """Event to signal application shutdown."""

        self.console = get_console()
        """Rich console for formatted output."""

        self.status: Status = Status("", console=self.console, spinner="dots")
        """Rich status indicator for CLI feedback."""

    async def shutdown(self, sig=None):
        """
        Handle graceful application shutdown.

        Args:
            sig: Signal that triggered shutdown (SIGTERM/SIGINT)

        Sets shutdown event and allows running operations to complete
        cleanly before terminating.
        """
        global _recv_signals

        if sig:
            _recv_signals += 1
            if _recv_signals >= 3:
                sys.exit(255)
            logger.warning(f"Received exit signal {sig}, count: {_recv_signals}")
            self.console.print(f"[bold red]Received exit signal {sig}[/bold red]")
        if not self.shutdown_event.is_set():
            self.shutdown_event.set()

    async def setup_signal_handlers(self):
        """
        Configure OS signal handlers.

        Handles:
        - SIGTERM for graceful termination
        - SIGINT for keyboard interrupts
        - Platform-specific signal routing
        - Async signal handling
        """
        if platform.system() == "Windows":
            try:
                signal.signal(
                    signal.SIGINT, lambda s, f: asyncio.create_task(self.shutdown(s))
                )
                signal.signal(
                    signal.SIGTERM, lambda s, f: asyncio.create_task(self.shutdown(s))
                )
            except (AttributeError, NotImplementedError):
                logger.warning("Signal handlers not fully supported on Windows")
        else:
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    asyncio.get_event_loop().add_signal_handler(
                        sig, lambda s=sig: asyncio.create_task(self.shutdown(s))  # type: ignore
                    )
                except NotImplementedError:
                    logger.warning(f"Failed to set handler for signal {sig}")

    def check_shutdown(self):
        """
        Check if shutdown has been requested.

        Raises:
            asyncio.CancelledError: If shutdown event is set
        """
        if self.shutdown_event and self.shutdown_event.is_set():
            raise asyncio.CancelledError()

    async def sleep(self):
        """
        Sleep for a configured delay while checking for shutdown.

        Note: this method is not precise and it is an intended behavior

        Raises:
            asyncio.CancelledError: If shutdown is requested during sleep
        """
        remaining = delay = self.config.app.delays.random()
        steps = 0.1
        cur_status = self.status.status

        logger.debug(f"Sleeping for {delay} seconds")
        while True:
            try:
                self.check_shutdown()
                self.status.update(
                    f"[yellow]Sleeping ({round(remaining, 1)})...[/yellow]"
                )
                await asyncio.sleep(steps)
                remaining -= steps
                if remaining <= 0:
                    break
            finally:
                self.status.update(cur_status)

    async def run(self, task: Callable[["Application"], Coroutine]):
        """
        Executed by start() to run the main application task.
        """
        from . import __version__

        if not asyncio.iscoroutinefunction(task):
            raise TypeError("The provided task must be an async function")

        global app_instance
        if app_instance is not None:
            raise exceptions.ApplicationAlreadyRunningError(
                "An application is already running"
            )
        app_instance = self

        self.status.update("Starting application...")
        self.status.start()

        text = f"cligram v{__version__}"
        if self.device.platform == utils.Platform.UNKNOWN:
            text += " on an unknown thing"
        elif self.device.platform == utils.Platform.ANDROID:
            text += " on Android!"
        self.console.print(f"[bold green]{text}[/bold green]")
        logger.info(
            f"Starting cligram application v{__version__} on {self.device.platform.value}"
        )

        self.status.update("Initializing...")
        # Setup platform-specific signal handlers
        await self.setup_signal_handlers()

        logger.debug(f"Loaded configuration: {self.config.path}")

        if self.config.updated:
            self.console.print("[bold yellow]Configuration file updated[/bold yellow]")
            logger.warning("Configuration updated with new fields")

        self.status.update("Loading state...")
        self.state.load()

        try:
            self.status.update("Running task...")
            await task(self)
            logger.info("Execution completed successfully")
        finally:
            self.status.update("Shutting down...")
            await self.state.save()
            await self.state.backup()
            logger.info("Application shutdown completed")
            self.status.stop()
            app_instance = None

    def start(self, task: Callable[["Application"], Coroutine]):
        """
        Initialize application and run the main task in the event loop.

        Initializes signal handlers, loads state, and executes the provided task.
        After task completion, saves state and performs cleanup.
        Raised exceptions are logged and re-raised.

        Args:
            task (Callable): Async function representing the main task to run

        Raises:
            ApplicationAlreadyRunningError: If an application is already running
            TypeError: If the provided task is not an async function
        """
        try:
            asyncio.run(self.run(task))
        except (asyncio.CancelledError, KeyboardInterrupt):
            logger.warning("Cancellation requested by user")
            self.console.print(
                "[bold yellow]Application stopped by user request[/bold yellow]"
            )
        except Exception as e:
            logger.fatal(f"Fatal error: {e}", exc_info=True)
            self.console.print(f"[bold red]Fatal error: {e}[/bold red]")
            raise
