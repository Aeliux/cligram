"""Main application module."""

import asyncio
import logging
import platform
import signal
import sys
from typing import TYPE_CHECKING, Callable, Coroutine

from rich import get_console
from rich.status import Status

from . import StateManager, utils

if TYPE_CHECKING:
    from . import Config

logger: logging.Logger = logging.getLogger(__name__)


class Application:
    """Main application class for cligram.

    Manages configuration, state, signal handling, and application lifecycle.
    """

    def __init__(self, config: "Config"):
        """Initialize the application with the given configuration."""
        self.config = config
        """Application configuration."""

        self.device: utils.DeviceInfo = utils.get_device_info()
        """Information about the current device."""

        self.state = StateManager(data_dir=self.config.path.data_path)
        """"State manager for application state persistence."""

        self.shutdown_event: asyncio.Event = asyncio.Event()
        """Event to signal application shutdown."""

        self.console = get_console()
        """Rich console for formatted output."""

        self.status: Status = Status("", console=self.console, spinner="dots")
        """Rich status indicator for CLI feedback."""

        self._recv_signals: int = 0
        """Count of received shutdown signals."""

        self._shutdown_callbacks: list[Callable[["Application"], None]] = []
        """Callbacks to execute on shutdown."""

    def add_shutdown_callback(self, callback: Callable[["Application"], None]) -> None:
        """Register a callback to be called on application shutdown.

        Args:
            callback: A callable that takes the application instance as an argument.
        """
        self._shutdown_callbacks.append(callback)

    def _run_shutdown_callbacks(self) -> None:
        """Execute all registered shutdown callbacks."""
        for callback in self._shutdown_callbacks:
            try:
                callback(self)
            except Exception as e:
                logger.error(
                    f"Error in shutdown callback {callback}: {e}", exc_info=True
                )

    def _shutdown(self, sig=None, frame=None) -> None:
        """Handle graceful application shutdown.

        Args:
            sig: Signal that triggered shutdown (SIGTERM/SIGINT)

        Sets shutdown event and allows running operations to complete
        cleanly before terminating.
        """
        global _recv_signals

        if sig:
            self._recv_signals += 1
            if self._recv_signals >= 3:
                sys.exit(255)
            logger.warning(f"Received exit signal {sig}, count: {self._recv_signals}")
            self.console.print(f"[bold red]Received exit signal {sig}[/bold red]")
        if not self.shutdown_event.is_set():
            self.shutdown_event.set()

    def _setup_signal_handlers(self):
        """Configure OS signal handlers.

        Handles:
        - SIGTERM for graceful termination
        - SIGINT for keyboard interrupts
        """
        if platform.system() == "Windows":
            try:
                signal.signal(signal.SIGINT, self._shutdown)
                signal.signal(signal.SIGTERM, self._shutdown)
            except (AttributeError, NotImplementedError):
                logger.warning("Signal handlers not fully supported on Windows")
        else:
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    asyncio.get_event_loop().add_signal_handler(sig, self._shutdown)
                except NotImplementedError:
                    logger.warning(f"Failed to set handler for signal {sig}")

    def _cleanup_signal_handlers(self):
        """Remove signal handlers and restore defaults."""
        if platform.system() == "Windows":
            try:
                signal.signal(signal.SIGINT, signal.SIG_DFL)
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
            except (AttributeError, NotImplementedError):
                pass
        else:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.remove_signal_handler(sig)
                except (NotImplementedError, ValueError):
                    pass

    def check_shutdown(self):
        """Check if shutdown has been requested.

        Raises:
            asyncio.CancelledError: If shutdown event is set
        """
        if self.shutdown_event and self.shutdown_event.is_set():
            raise asyncio.CancelledError()

    async def sleep(self):
        """Sleep for a configured delay while checking for shutdown.

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

    async def _run(
        self, task: Callable[["Application"], Coroutine] | Coroutine
    ) -> None:
        """Executed by start() to run the main application task."""
        from . import __version__

        if asyncio.iscoroutine(task):
            coro = task
        elif asyncio.iscoroutinefunction(task):
            coro = task(self)
        else:
            raise TypeError("Task must be a coroutine or async callable")

        utils.core._set_running_application(self)

        self.status.update("Starting application...")
        self.status.start()

        text = f"cligram v{__version__}"
        if self.device.platform == utils.device.Platform.UNKNOWN:
            text += " on an unknown thing"
        elif self.device.platform == utils.device.Platform.ANDROID:
            text += " on Android!"
        self.console.print(f"[bold green]{text}[/bold green]")
        logger.info(
            f"Starting cligram application v{__version__} on {self.device.platform.value}"
        )

        self.status.update("Initializing...")
        # Setup platform-specific signal handlers
        self._setup_signal_handlers()

        logger.debug(f"Loaded configuration: {self.config.path.config_path}")

        if self.config.updated:
            self.console.print("[bold yellow]Configuration file updated[/bold yellow]")
            logger.warning("Configuration updated with new fields")

        self.status.update("Loading state...")
        await self.state.load()

        try:
            self.status.update("Running task...")
            await coro
            logger.info("Execution completed successfully")
        finally:
            logger.info("Shutting down application")
            self.status.update("Shutting down...")
            await self.state.save()
            self.state.backup()
            self.status.stop()
            self._run_shutdown_callbacks()
            self._cleanup_signal_handlers()
            logger.info("Application shutdown completed")

    def start(self, task: Callable[["Application"], Coroutine] | Coroutine) -> None:
        """Initialize application and run the main task in the event loop.

        Initializes signal handlers, loads state, and executes the provided task.
        After task completion, saves state and performs cleanup.
        Raised exceptions are logged and re-raised.

        Args:
            task: Either an async function that accepts Application, or a coroutine

        Raises:
            ApplicationAlreadyRunningError: If an application is already running
            TypeError: If the provided task is not awaitable
        """
        try:
            asyncio.run(self._run(task))
        except (asyncio.CancelledError, KeyboardInterrupt):
            logger.warning("Cancellation requested by user")
            self.console.print(
                "[bold yellow]Application stopped by user request[/bold yellow]"
            )
        except Exception as e:
            logger.fatal(f"Fatal error: {e}", exc_info=True)
            self.console.print(f"[bold red]Fatal error: {e}[/bold red]")
            raise
