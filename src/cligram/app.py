import asyncio
import logging
import platform
import signal
import time
from pathlib import Path
from typing import Optional

from .config import Config, WorkMode
from .scanner import TelegramScanner
from .state_manager import StateManager

logger = None  # Global logger instance


class Application:
    """
    Core application orchestrator.

    Responsibilities:
    - Load and manage configuration
    - Initialize and coordinate components
    - Handle shutdown and cleanup
    - Manage application lifecycle
    """

    def __init__(self, config: Config):
        """
        Initialize application components.

        Args:
            config: Loaded configuration object
            **kwargs: CLI argument overrides including:
                - verbose: Enable debug logging
                - test: Enable test mode
                - mode: Operation mode
                - session: Session name
                - proxy: Override proxy URL
                - exclude: Path to exclusions file
        """
        self.config = config
        # Initialize global logger with config
        global logger
        logger = logging.getLogger("cligram.app")

        self.state = StateManager(
            data_dir=self.config.data_path,
            backup_dir=self.config.data_path / "backup",
        )
        self.scanner = TelegramScanner(self.config, self.state)
        self._shutdown_event: Optional[asyncio.Event] = None

    async def shutdown(self, sig=None):
        """
        Handle graceful application shutdown.

        Args:
            signal_: Signal that triggered shutdown (SIGTERM/SIGINT)

        Sets shutdown event and allows running operations to complete
        cleanly before terminating.
        """
        if sig:
            logger.warning(f"[APP] Received exit signal {sig}")
        if self._shutdown_event:
            self._shutdown_event.set()

        if False:
            # Cancel all running tasks except the current one
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            logger.warning(f"[APP] Cancelling {len(tasks)} running tasks")

            for task in tasks:
                task.cancel()

            # Wait for all tasks to complete cancellation
            await asyncio.gather(*tasks, return_exceptions=True)

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
                logger.warning("[APP] Signal handlers not fully supported on Windows")
        else:
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    asyncio.get_event_loop().add_signal_handler(
                        sig, lambda s=sig: asyncio.create_task(self.shutdown(s))
                    )
                except NotImplementedError:
                    logger.warning(f"[APP] Failed to set handler for signal {sig}")

    def log_progress(self):
        """
        Log current application state progress.
        """
        logger.info(f"[INFO] Total Eligible users: {len(self.state.users.eligible)}")
        logger.info(f"[INFO] Total Messaged users: {len(self.state.users.messaged)}")

    async def run(self):
        """
        Execute main application loop.

        Flow:
        1. Initialize shutdown event
        2. Setup signal handlers
        3. Load application state
        4. Run scanner in configured mode
        5. Handle cleanup on completion
        """
        self._shutdown_event = asyncio.Event()

        logger.info(f"[APP] Starting application in {self.config.app.mode.value} mode")
        if self.config.app.verbose:
            logger.debug("[APP] Debug logging enabled")
            logger.debug(f"[APP] Loaded configuration: {self.config.path}")

        if self.config.updated:
            logger.warning("[APP] Configuration updated with new fields")

        # Setup platform-specific signal handlers
        await self.setup_signal_handlers()
        self.state.load()
        self.log_progress()

        try:
            await self.scanner.run(self._shutdown_event)
            logger.info("[APP] Execution completed successfully")
        except Exception as e:
            logger.error(f"[APP] Error during execution: {e}")
            raise
        finally:
            self.log_progress()
            await self.state.save()
            await self.state.backup()
            logger.info("[APP] Shutdown complete")

    def start(self):
        """
        Application entry point.

        Wraps async run() method in synchronous interface.
        Handles keyboard interrupts and unexpected errors.
        """
        try:
            asyncio.run(self.run())
        except asyncio.CancelledError:
            logger.warning("[APP] Cancellation requested by user")
        except KeyboardInterrupt:
            logger.warning("[APP] Interrupted by user")
        except Exception as e:
            logger.error(f"[APP] Fatal error: {e}")
            raise
