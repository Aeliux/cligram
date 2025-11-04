class SessionMismatchError(Exception):
    """Raised when the session's API ID does not match the configured API ID."""

    pass


class SessionNotFoundError(Exception):
    """Raised when the specified session file is not found."""

    pass
