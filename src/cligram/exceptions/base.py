class CligramError(Exception):
    """Base exception class for cligram errors."""

    pass


class VersionError(CligramError):
    """Raised when there is a version-related error."""

    pass


class InvalidPathError(CligramError):
    """Exception raised for invalid file or directory paths."""

    pass
