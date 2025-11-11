class CligramError(Exception):
    """Base exception class for cligram errors."""

    pass


class VersionError(CligramError):
    """Raised when there is a version-related error."""

    pass
