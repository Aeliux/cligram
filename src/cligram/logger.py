import hashlib
import logging
import re
from logging import FileHandler
from pathlib import Path
from typing import Optional

from colorama import Fore, Style, init

init(autoreset=True)  # Initialize colorama


class ColorGenerator:
    """
    Color scheme manager for log messages.

    Provides consistent color assignments for logging scopes using
    deterministic hashing to maintain color consistency across runs.
    """

    COLORS = [
        Fore.CYAN,  # Used for info/status messages
        Fore.GREEN,  # Success indicators
        Fore.YELLOW,  # Warnings and delays
        Fore.MAGENTA,  # Scanning operations
        Fore.BLUE,  # Processing operations
        Fore.RED,  # Errors and failures
        Fore.WHITE,  # Default/fallback color
    ]

    @staticmethod
    def get_color_for_scope(scope: str) -> str:
        """
        Get ANSI color code for a logging scope.

        Args:
            scope: Scope identifier (e.g., 'error', 'warning', 'scan')

        Returns:
            str: ANSI color code for the scope
        """
        if scope == "error":
            return Fore.RED
        elif scope in ["warning", "delay", "test"]:
            return Fore.YELLOW
        elif scope in ["complete", "success", "done"]:
            return Fore.GREEN
        elif scope in ["app", "proxy", "process", "msg", "user", "info"]:
            return Fore.CYAN
        elif scope in ["stats", "state", "summary"]:
            return Fore.LIGHTBLACK_EX
        elif scope == "scan":
            return Fore.MAGENTA
        elif scope == "send":
            return Fore.BLUE

        # Use hash to get consistent index
        hash_val = int(hashlib.md5(scope.encode()).hexdigest(), 16)
        color_idx = hash_val % len(ColorGenerator.COLORS)
        return ColorGenerator.COLORS[color_idx]


_logger: Optional[logging.Logger] = None
_initialized: bool = False


class ColoredFormatter(logging.Formatter):
    """
    Log formatter with ANSI color support.

    Features:
    - Scope-based coloring ([SCAN], [USER], etc.)
    - Level-based message coloring (errors, warnings)
    - Color reset after each message
    - Regex-based scope detection
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize formatter with color settings.

        Configures:
        - Scope detection pattern
        - Error/warning colors
        - ANSI color support
        """
        super().__init__(*args, **kwargs)
        self.scope_pattern = re.compile(r"\[([A-Z_]+)\]")
        # Special handling for errors
        self.error_color = Fore.RED

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()

        # Color errors regardless of scope
        if record.levelno >= logging.ERROR:
            return f"{self.error_color}{message}{Style.RESET_ALL}"
        elif record.levelno >= logging.WARNING:
            return f"{Fore.YELLOW}{message}{Style.RESET_ALL}"

        # Find and color all scopes dynamically
        def replace_scope(match):
            scope = match.group(1)
            color = ColorGenerator.get_color_for_scope(scope.lower())
            return f"{color}[{scope}]{Style.RESET_ALL}"

        return self.scope_pattern.sub(replace_scope, message)


def setup_logger(
    verbose: bool = False, log_file: str = "cligram.log"
) -> logging.Logger:
    """
    Initialize application logger with console and file outputs.

    Args:
        verbose: Enable debug level console logging
        log_file: Path to log file

    Returns:
        Logger: Configured logger instance
    """
    global _logger, _initialized
    if not _initialized:
        logger = logging.getLogger("cligram")
        logger.setLevel(logging.DEBUG)

        # Console handler with colors
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG if verbose else logging.INFO)
        ch_formatter = ColoredFormatter("%(message)s")
        ch.setFormatter(ch_formatter)

        # File handler with rotation
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh_formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
        fh.setFormatter(fh_formatter)

        logger.handlers.clear()
        logger.addHandler(ch)
        logger.addHandler(fh)

        _logger = logger
        _initialized = True
    return _logger


def get_logger() -> logging.Logger:
    if not _initialized:
        raise RuntimeError("Logger not initialized. Must call setup_logger first.")
    return _logger
