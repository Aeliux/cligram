# import everything from submodules
from .base import CligramError, VersionError, InvalidPathError  # isort:skip
from .application import (
    ApplicationAlreadyRunningError,
    ApplicationError,
    ApplicationNotRunningError,
)
from .archive import (
    ArchiveError,
    EmptyArchiveError,
    InvalidArchiveError,
    InvalidCompressionTypeError,
    InvalidPasswordError,
    SizeLimitExceededError,
)
from .config import ConfigError, ConfigSearchError
from .connection import ConnectionError, NoWorkingConnectionError
from .session import SessionError, SessionMismatchError, SessionNotFoundError

__all__ = [
    "CligramError",
    "VersionError",
    "ConnectionError",
    "NoWorkingConnectionError",
    "SessionError",
    "SessionMismatchError",
    "SessionNotFoundError",
    "ApplicationError",
    "ApplicationNotRunningError",
    "ApplicationAlreadyRunningError",
    "ConfigError",
    "ConfigSearchError",
    "ArchiveError",
    "InvalidArchiveError",
    "InvalidPasswordError",
    "InvalidCompressionTypeError",
    "SizeLimitExceededError",
    "EmptyArchiveError",
    "InvalidPathError",
]
