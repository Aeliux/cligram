from . import CligramError


class ConnectionError(CligramError):
    """Raised when a connection error occurs."""

    pass


class NoWorkingConnectionError(ConnectionError):
    """Raised when no working connection (direct or proxy) is available."""

    pass
