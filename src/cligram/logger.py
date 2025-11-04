import hashlib
import logging
import re
from logging import FileHandler
from pathlib import Path
from typing import Optional


class ColoredNameFormatter(logging.Formatter):
    """Formatter that assigns consistent colors to logger names using Rich markup."""

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
        super().__init__(fmt, datefmt, style)
        self._color_cache = {}

    def _get_color_for_name(self, name: str) -> str:
        """Get consistent color for a logger name using hash."""
        if name not in self._color_cache:
            # Use hash to consistently map names to colors
            hash_value = int(hashlib.md5(name.encode()).hexdigest(), 16)
            color_index = hash_value % len(self.COLORS)
            self._color_cache[name] = self.COLORS[color_index]
        return self._color_cache[name]

    def format(self, record):
        # Color the logger name
        original_name = record.name
        color = self._get_color_for_name(original_name)
        record.name = f"[{color}]{original_name}[/{color}]"

        result = super().format(record)

        # Restore original name
        record.name = original_name
        return result


def setup_logger(verbose: bool = False, log_file: str = "cligram.log"):
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

    if verbose:
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
