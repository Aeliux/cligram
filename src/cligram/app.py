import asyncio
import logging
import platform
import signal
import sys
from typing import Callable, Optional

from rich import get_console
from rich.status import Status

from .config import Config, ScanMode
from .state_manager import StateManager

logger = None  # Global logger instance
app_instance: Optional["Application"] = None
_recv_signals: int = 0


def get_app() -> "Application":
    """
    Retrieve the global application instance.

    Returns:
        Application: The global application instance

    Raises:
        RuntimeError: If application is not initialized
    """
    global app_instance
    if app_instance is None:
        raise RuntimeError("Application instance is not initialized")
    return app_instance


class Application:
    def __init__(self, config: Config):
        global logger

        self.config = config

        logger = logging.getLogger("cligram.app")

        self.state = StateManager(data_dir=self.config.data_path)
        """"State manager for application state persistence."""

        self.shutdown_event: asyncio.Event = asyncio.Event()
        """Event to signal application shutdown."""

        self.console = get_console()
        """Rich console for formatted output."""
        self.status: Optional[Status] = None
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
                        sig, lambda s=sig: asyncio.create_task(self.shutdown(s))
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

    async def run(self, task: Callable[["Application"], asyncio.Future]):
        """
        Initialize application and run task.
        """
        from . import __version__

        global app_instance
        if app_instance is not None:
            raise RuntimeError("Application instance is already running")
        app_instance = self

        self.status = Status(
            "Starting application...", console=self.console, spinner="dots"
        )
        self.status.start()

        self.console.print(f"[bold green]cligram v{__version__}[/bold green]")
        logger.info(f"Starting application v{__version__}")

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
        except Exception as e:
            logger.error(f"Error during execution: {e}")
            raise
        finally:
            self.status.update("Shutting down...")
            await self.state.save()
            await self.state.backup()
            logger.info("Shutdown complete")
            self.status.stop()
            app_instance = None

    def start(self, task: Callable[["Application"], asyncio.Future]):
        """
        Start the application event loop and run the specified task.

        Args:
            task (Callable): Async function representing the main task to run
        """
        if app_instance is not None:
            raise RuntimeError("Application instance is already running")

        if not callable(task):
            raise ValueError("Task must be a callable async function")

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
