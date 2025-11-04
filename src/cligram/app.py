import asyncio
import logging
import platform
import signal
from typing import Optional

from rich import get_console
from rich.status import Status

from .config import Config, WorkMode
from .state_manager import StateManager

logger = None  # Global logger instance

app_instance: Optional["Application"] = None


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

        self.scanner = None
        self.shutdown_event: Optional[asyncio.Event] = None
        """Event to signal application shutdown."""

        self.console = get_console()
        """Rich console for formatted output."""
        self.status: Optional[Status] = None
        """Rich status indicator for CLI feedback."""

    async def shutdown(self, sig=None):
        """
        Handle graceful application shutdown.

        Args:
            signal_: Signal that triggered shutdown (SIGTERM/SIGINT)

        Sets shutdown event and allows running operations to complete
        cleanly before terminating.
        """
        if sig:
            logger.warning(f"Received exit signal {sig}")
        if self.shutdown_event:
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

    def log_progress(self):
        """
        Log current application state progress.
        """
        logger.info(f"Total Eligible users: {len(self.state.users.eligible)}")
        logger.info(f"Total Messaged users: {len(self.state.users.messaged)}")

    async def run(self):
        """
        Main application execution method.
        """
        from . import __version__

        global app_instance
        app_instance = self

        self.shutdown_event = asyncio.Event()
        self.status = Status(
            "Starting application...", console=self.console, spinner="dots"
        )
        self.status.start()

        self.console.print(f"[bold green]cligram v{__version__}[/bold green]")
        logger.info(f"Starting application in {self.config.app.mode.value} mode")

        self.status.update("Initializing...")
        # Setup platform-specific signal handlers
        await self.setup_signal_handlers()

        logger.debug(f"Loaded configuration: {self.config.path}")

        if self.config.updated:
            logger.warning("Configuration updated with new fields")

        self.status.update("Loading state...")
        self.state.load()
        self.log_progress()

        try:
            from .scanner import TelegramScanner

            self.status.update("Running scanner...")
            self.scanner = TelegramScanner(self)
            await self.scanner.run(self.shutdown_event)
            logger.info("Execution completed successfully")
        except Exception as e:
            logger.error(f"Error during execution: {e}")
            raise
        finally:
            self.status.update("Shutting down...")
            self.log_progress()
            await self.state.save()
            await self.state.backup()
            logger.info("[APP] Shutdown complete")
            self.status.stop()

    def start(self):
        """
        Application entry point.

        Wraps async run() method in synchronous interface.
        Handles keyboard interrupts and unexpected errors.
        """
        try:
            asyncio.run(self.run())
        except asyncio.CancelledError:
            logger.warning("Cancellation requested by user")
        except KeyboardInterrupt:
            logger.warning("Interrupted by user")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            raise
