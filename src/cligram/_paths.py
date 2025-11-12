"""Default paths used by Cligram for configuration and data storage."""

from pathlib import Path

DEFAULT_PATH = Path.home() / ".cligram"
"""Default base path for Cligram configuration and data."""

GLOBAL_CONFIG_PATH = DEFAULT_PATH / "config.json"
"""Path to the global configuration file."""

DEFAULT_LOGS_PATH = DEFAULT_PATH / "logs"
"""Default directory for log files."""
