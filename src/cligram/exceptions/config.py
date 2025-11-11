from . import CligramError


class ConfigError(CligramError):
    """Base exception class for configuration-related errors."""

    pass


class ConfigSearchError(ConfigError):
    """Raised when there is an error searching for the configuration file."""

    pass
