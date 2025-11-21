from . import CligramError


class ArchiveError(CligramError):
    """Base exception for archive-related errors in cligram."""

    pass


class InvalidArchiveError(ArchiveError):
    """Exception raised for invalid or corrupted archive files."""

    pass


class InvalidPasswordError(ArchiveError):
    """Exception raised for incorrect passwords when accessing encrypted archives."""

    pass


class InvalidCompressionTypeError(ArchiveError):
    """Exception raised for unsupported compression types in archives."""

    pass


class SizeLimitExceededError(ArchiveError):
    """Exception raised when an archive exceeds the maximum allowed size."""

    pass


class EmptyArchiveError(InvalidArchiveError):
    """Exception raised when attempting to access an empty archive."""

    pass
