"""CLI based telegram client."""

from ._paths import DEFAULT_LOGS_PATH, DEFAULT_PATH, GLOBAL_CONFIG_PATH  # isort:skip
from .__version__ import __version__  # isort:skip

from . import exceptions, utils  # isort:skip
from .state_manager import StateManager  # isort:skip
from .config import Config, InteractiveMode, ScanMode  # isort:skip
from .proxy_manager import Proxy, ProxyManager  # isort:skip
from .app import Application
from .session import CustomSession

__all__ = [
    "DEFAULT_PATH",
    "GLOBAL_CONFIG_PATH",
    "DEFAULT_LOGS_PATH",
    "__version__",
    "Application",
    "Config",
    "ScanMode",
    "StateManager",
    "CustomSession",
    "utils",
    "ProxyManager",
    "Proxy",
    "InteractiveMode",
    "exceptions",
]
