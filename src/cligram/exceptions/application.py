from . import CligramError


class ApplicationError(CligramError):
    """Base exception class for application-related errors."""

    pass


class ApplicationNotRunningError(ApplicationError):
    """Raised when there is an attempt to perform an operation that requires the application to be running."""

    pass


class ApplicationAlreadyRunningError(ApplicationError):
    """Raised when there is an attempt to start the application while it is already running."""

    pass
