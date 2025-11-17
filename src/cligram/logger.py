"""Logger setup with colored logger names using Rich markup."""

import hashlib
import logging
import time
from logging import FileHandler
from pathlib import Path
from typing import TYPE_CHECKING

from . import DEFAULT_LOGS_PATH

if TYPE_CHECKING:
    from . import Config


class ColoredNameFormatter(logging.Formatter):
    """Logging formatter with colored logger names using Rich markup."""

    # Rich color palette for logger names (distinct, readable colors)
    COLORS = [
        "cyan",
        "magenta",
        "green",
        "yellow",
        "blue",
        "bright_cyan",
        "bright_magenta",
        "bright_green",
        "bright_yellow",
        "bright_blue",
        "deep_sky_blue1",
        "medium_purple",
        "spring_green1",
        "gold1",
        "orange1",
    ]

    def __init__(self, fmt=None, datefmt=None, style="%"):
        """Initialize the ColoredNameFormatter."""
        super().__init__(fmt, datefmt, style)  # type: ignore
        self._color_cache = {}

    def _get_color_for_name(self, name: str) -> str:
        """Get consistent color for a logger name using hash."""
        if name not in self._color_cache:
            # Use hash to consistently map names to colors
            hash_value = int(hashlib.md5(name.encode()).hexdigest(), 16)  # nosec
            color_index = hash_value % len(self.COLORS)
            self._color_cache[name] = self.COLORS[color_index]
        return self._color_cache[name]

    def format(self, record):
        """Format the log record with colored logger name."""
        # Color the logger name
        original_name = record.name
        color = self._get_color_for_name(original_name)
        record.name = f"[{color}]{original_name}[/{color}]"

        result = super().format(record)

        # Restore original name
        record.name = original_name
        return result


def setup_preinit_logger():
    """Setup a basic logger for pre-init stage logging.

    it creates a log file in the default logs path
    with the preinit prefix and current date.
    """
    log_path = Path(DEFAULT_LOGS_PATH / f"preinit-{_get_date()}.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        filename=log_path,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def setup_logger(config: "Config"):
    """Setup the logger based on the provided configuration.

    Args:
        config (Config): The configuration object containing logging settings.
    """
    log_file = config.base_path / "logs" / f"{_get_date()}.log"

    logging.basicConfig(
        level=logging.DEBUG,
    )

    logger = logging.getLogger()
    for h in logger.handlers[:]:
        logger.removeHandler(h)
        h.close()

    # add file handler
    logger.handlers
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh_formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh.setFormatter(fh_formatter)
    logger.addHandler(fh)

    if config.app.verbose:
        # Add rich logging for console output
        from rich.logging import RichHandler

        console_handler = RichHandler(
            markup=True,
            omit_repeated_times=False,
        )
        console_handler.setLevel(logging.DEBUG)
        console_formatter = ColoredNameFormatter("%(name)s: %(message)s")
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)


def _get_date():
    """Get the current date as a string in YYYY-MM-DD format."""
    return time.strftime("%Y-%m-%d", time.localtime())
