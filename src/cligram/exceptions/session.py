from . import CligramError


class SessionError(CligramError):
    """Base exception class for session-related errors."""

    pass


class SessionMismatchError(SessionError):
    """Raised when the session's API ID does not match the configured API ID."""

    pass


class SessionNotFoundError(SessionError, FileNotFoundError):
    """Raised when the specified session file is not found."""

    pass
