"""Application configuration management."""

import base64
import hashlib
import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, overload

from . import GLOBAL_CONFIG_PATH, exceptions

_config_instance: Optional["Config"] = None
logger = logging.getLogger(__name__)


class ScanMode(Enum):
    """Operation modes for the scanner."""

    FULL = "full"
    """Full operation mode: scans and sends messages to targets."""

    SCAN = "scan"
    """Scan mode: only scans and stores eligible usernames without sending."""

    SEND = "send"
    """Send mode: only sends messages to eligible usernames without scanning."""

    HALT = "halt"
    """Halt mode: logs in to telegram and shuts down."""

    RECEIVE = "receive"
    """Receive mode: receives and shows new messages."""

    LOGOUT = "logout"
    """Logout mode: logs out from the Telegram and deletes the session file."""


@dataclass
class ApiConfig:
    """Telegram API credentials."""

    id: int = 0
    """Telegram API ID obtained from my.telegram.org/apps"""

    hash: str = ""
    """Telegram API hash string obtained from my.telegram.org/apps"""

    from_env: bool = field(init=False, default=False)
    """Indicates if the credentials were loaded from environment variables"""

    @property
    def identifier(self) -> str:
        """Get unique identifier for the API credentials."""
        hasher = hashlib.sha256()
        hasher.update(f"{self.id}:{self.hash}".encode("utf-8"))
        digest = hasher.digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8")[:8]

    def __post_init__(self):
        self._load_from_env()

        if not isinstance(self.id, int):
            raise ValueError("API ID must be an integer")
        if not isinstance(self.hash, str):
            raise ValueError("API hash must be a string")

    def __str__(self) -> str:
        return "ApiConfig(id=***, hash=***)"

    def __repr__(self) -> str:
        return str(self)

    def _load_from_env(self) -> None:
        """Load API credentials from environment variables."""
        import os

        api_id = os.getenv("CLIGRAM_API_ID")
        api_hash = os.getenv("CLIGRAM_API_HASH")
        self.from_env = all([api_id, api_hash])
        if not self.from_env:
            return

        if api_id is not None:
            try:
                self.id = int(api_id)
            except ValueError:
                raise ValueError(
                    "Environment variable CLIGRAM_API_ID must be an integer"
                )

        if api_hash is not None:
            self.hash = api_hash

    def _intercept(self, attr: str) -> Any:
        if attr == "identifier":
            return self.identifier
        elif attr in ("id", "hash"):
            return "***REDACTED***"
        return getattr(self, attr)

    def _intercept_set(self, attr: str, value: Any) -> None:
        if attr in ("id", "hash") and self.from_env:
            raise RuntimeError(
                "Cannot modify API credentials loaded from environment variables"
            )

        setattr(self, attr, value)

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "ApiConfig":
        return cls(
            id=data.get("id", cls.__dataclass_fields__["id"].default),
            hash=data.get("hash", cls.__dataclass_fields__["hash"].default),
        )

    def _to_dict(self) -> Dict[str, Any]:
        return (
            {
                "id": self.__dataclass_fields__["id"].default,
                "hash": self.__dataclass_fields__["hash"].default,
            }
            if self.from_env
            else {"id": self.id, "hash": self.hash}
        )


@dataclass
class DelayConfig:
    """Delay interval configuration."""

    min: float = 10.0
    """Minimum delay in seconds"""

    max: float = 20.0
    """Maximum delay in seconds"""

    def random(self) -> float:
        """Generate random delay within configured bounds"""
        return random.uniform(self.min, self.max)

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "DelayConfig":
        return cls(
            min=data.get("min", cls.__dataclass_fields__["min"].default),
            max=data.get("max", cls.__dataclass_fields__["max"].default),
        )

    def _to_dict(self) -> Dict[str, Any]:
        return {"min": self.min, "max": self.max}


@dataclass
class LongDelayConfig(DelayConfig):
    """Configuration for long delay periods."""

    min: float = 30.0
    max: float = 60.0

    chance: float = 0.1
    """Probability (0-1) of taking a long delay instead of normal delay"""

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "LongDelayConfig":
        return cls(
            min=data.get("min", cls.__dataclass_fields__["min"].default),
            max=data.get("max", cls.__dataclass_fields__["max"].default),
            chance=data.get("chance", cls.__dataclass_fields__["chance"].default),
        )

    def _to_dict(self) -> Dict[str, Any]:
        return {"min": self.min, "max": self.max, "chance": self.chance}


@dataclass
class DelaysConfig:
    """Delay timing configuration."""

    normal: DelayConfig = field(default_factory=DelayConfig)
    """Normal delay settings"""

    long: LongDelayConfig = field(default_factory=LongDelayConfig)
    """Long break delay settings"""

    def random(self) -> float:
        """Generate a random delay based on configured normal and long delays.

        Returns:
            float: Random delay duration in seconds
        """
        delay: float
        if random.random() < self.long.chance:
            delay = self.long.random()
        else:
            delay = self.normal.random()

        delay = round(delay, 1)
        return delay

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "DelaysConfig":
        return cls(
            normal=DelayConfig._from_dict(data.get("normal", {})),
            long=LongDelayConfig._from_dict(data.get("long", {})),
        )

    def _to_dict(self) -> Dict[str, Any]:
        return {"normal": self.normal._to_dict(), "long": self.long._to_dict()}


@dataclass
class MessagesConfig:
    """Configuration for message forwarding."""

    source: str = "me"
    """Source of messages to forward ('me' or channel username)"""

    limit: int = 20
    """Maximum number of messages to be loaded from source"""

    msg_id: Optional[int] = None
    """Specific message ID to forward (optional)"""

    @property
    def randomize(self) -> bool:
        """Determine if message selection should be randomized."""
        return self.msg_id is None

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "MessagesConfig":
        return cls(
            source=data.get("source", cls.__dataclass_fields__["source"].default),
            limit=data.get("limit", cls.__dataclass_fields__["limit"].default),
            msg_id=data.get("msg_id", cls.__dataclass_fields__["msg_id"].default),
        )

    def _to_dict(self) -> Dict[str, Any]:
        return {"source": self.source, "limit": self.limit, "msg_id": self.msg_id}


@dataclass
class ScanConfig:
    """Configuration for scanning behavior and timing."""

    messages: MessagesConfig = field(default_factory=MessagesConfig)
    """Message forwarding settings"""

    mode: ScanMode = ScanMode.FULL
    """Operation mode"""

    targets: List[str] = field(default_factory=list)  # type: ignore
    """List of target groups to scan (usernames or URLs)"""

    limit: int = 50
    """Maximum number of messages to scan per group"""

    test: bool = False
    """Test mode without sending messages"""

    rapid_save: bool = False
    """Enable rapid state saving to disk"""

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "ScanConfig":
        return cls(
            messages=MessagesConfig._from_dict(data.get("messages", {})),
            mode=ScanMode(
                data.get("mode", cls.__dataclass_fields__["mode"].default.value)
            ),
            targets=data.get(
                "targets",
                cls.__dataclass_fields__["targets"].default_factory(),  # type: ignore
            ),
            limit=data.get("limit", cls.__dataclass_fields__["limit"].default),
            test=data.get("test", cls.__dataclass_fields__["test"].default),
            rapid_save=data.get(
                "rapid_save", cls.__dataclass_fields__["rapid_save"].default
            ),
        )

    def _to_dict(self) -> Dict[str, Any]:
        return {
            "messages": self.messages._to_dict(),
            "mode": self.mode.value,
            "targets": self.targets,
            "limit": self.limit,
            "test": self.test,
            "rapid_save": self.rapid_save,
        }


@dataclass
class ConnectionConfig:
    """Connection settings for Telegram client."""

    direct: bool = True
    """Whether to allow direct connection"""

    proxies: List[str] = field(default_factory=list)  # type: ignore
    """List of proxy URLs to try for connection"""

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "ConnectionConfig":
        return cls(
            direct=data.get(
                "direct",
                cls.__dataclass_fields__["direct"].default,
            ),
            proxies=data.get(
                "proxies",
                cls.__dataclass_fields__["proxies"].default_factory(),  # type: ignore
            ),
        )

    def _to_dict(self) -> Dict[str, Any]:
        return {
            "direct": self.direct,
            "proxies": self.proxies,
        }


@dataclass
class StartupConfig:
    """Telegram client startup settings."""

    count_unread_messages: bool = True
    """Show unread messages count on startup"""

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "StartupConfig":
        return cls(
            count_unread_messages=data.get(
                "count_unread_messages",
                cls.__dataclass_fields__["count_unread_messages"].default,
            ),
        )

    def _to_dict(self) -> Dict[str, Any]:
        return {
            "count_unread_messages": self.count_unread_messages,
        }


@dataclass
class TelegramConfig:
    """Telegram client settings."""

    api: ApiConfig = field(default_factory=ApiConfig)
    """API credentials from my.telegram.org"""

    connection: ConnectionConfig = field(default_factory=ConnectionConfig)
    """Connection settings"""

    startup: StartupConfig = field(default_factory=StartupConfig)
    """Startup behavior settings"""

    session: str = "default"
    """Session file name for persistent authorization"""

    impersonate: bool = False
    """Impersonate device info from session metadata"""

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "TelegramConfig":
        return cls(
            api=ApiConfig._from_dict(data.get("api", {})),
            connection=ConnectionConfig._from_dict(data.get("connection", {})),
            startup=StartupConfig._from_dict(data.get("startup", {})),
            session=data.get("session", cls.__dataclass_fields__["session"].default),
            impersonate=data.get(
                "impersonate", cls.__dataclass_fields__["impersonate"].default
            ),
        )

    def _to_dict(self) -> Dict[str, Any]:
        return {
            "api": self.api._to_dict(),
            "connection": self.connection._to_dict(),
            "startup": self.startup._to_dict(),
            "session": self.session,
            "impersonate": self.impersonate,
        }


@dataclass
class AppConfig:
    """Main application behavior configuration."""

    delays: DelaysConfig = field(default_factory=DelaysConfig)
    """Delay timing configurations"""

    verbose: bool = False
    """Enable debug logging"""

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        return cls(
            delays=DelaysConfig._from_dict(data.get("delays", {})),
            verbose=data.get("verbose", cls.__dataclass_fields__["verbose"].default),
        )

    def _to_dict(self) -> Dict[str, Any]:
        return {
            "delays": self.delays._to_dict(),
            "verbose": self.verbose,
        }


class InteractiveMode(Enum):
    """Interactive mode options."""

    CLIGRAM = "cligram"
    """Interactive mode with Cligram commands"""

    PYTHON = "python"
    """Interactive mode with Python code execution"""


@dataclass
class InteractiveConfig:
    """Interactive mode configuration."""

    mode: InteractiveMode = InteractiveMode.CLIGRAM
    """The interactive mode to use"""

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "InteractiveConfig":
        return cls(
            mode=InteractiveMode(
                data.get("mode", cls.__dataclass_fields__["mode"].default.value)
            )
        )

    def _to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
        }


@dataclass
class Config:
    """Application configuration root."""

    app: AppConfig = field(default_factory=AppConfig)
    """Application behavior settings"""

    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    """Telegram client and connection settings"""

    scan: ScanConfig = field(default_factory=ScanConfig)
    """Scanning behavior and timing settings"""

    interactive: InteractiveConfig = field(default_factory=InteractiveConfig)
    """Interactive mode settings"""

    exclusions: List[str] = field(default_factory=list)
    """List of usernames to exclude from processing"""

    path: Path = field(default=Path("config.json"))
    """Path to the configuration file"""

    updated: bool = False
    """Indicates if the configuration was updated with new fields"""

    overridden: bool = False
    """Indicates if the configuration was overridden via CLI"""

    temp: Dict[str, Any] = field(default_factory=dict)
    """Temporary in-memory configuration data"""

    @property
    def base_path(self) -> Path:
        """Get base directory of the configuration file."""
        return self.path.parent

    @property
    def data_path(self) -> Path:
        """Get data directory path."""
        return self.base_path / "data"

    @overload
    @classmethod
    def get_config(cls, raise_if_failed: Literal[True]) -> "Config": ...

    @overload
    @classmethod
    def get_config(cls, raise_if_failed: Literal[False]) -> Optional["Config"]: ...

    @classmethod
    def get_config(cls, raise_if_failed: bool = True) -> Optional["Config"]:
        """Get application configurations."""
        if raise_if_failed:
            if _config_instance is None:
                raise RuntimeError("Configuration not loaded. Call from_file() first.")
            if not isinstance(_config_instance, cls):
                raise TypeError("Configuration instance is of incorrect type.")

        config = _config_instance if isinstance(_config_instance, cls) else None
        if config is not None:
            logger.info("Using existing configuration instance.")

        return config  # type: ignore

    @classmethod
    def from_file(
        cls,
        config_path: str | Path = "config.json",
        overrides: Optional[List[str]] = None,
    ) -> "Config":
        """Load configuration from JSON file."""
        logger.info(f"Loading configuration from file: {config_path}")
        config_full_path = Path(config_path).resolve()
        if not config_full_path.exists():
            logger.error(f"Configuration file not found: {config_path}")
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_full_path, "r") as f:
            original_data = json.load(f)
        logger.info("Configuration file loaded successfully.")

        # Parse main sections
        logger.info("Parsing configuration")
        config = cls(
            app=AppConfig._from_dict(original_data.get("app", {})),
            telegram=TelegramConfig._from_dict(original_data.get("telegram", {})),
            scan=ScanConfig._from_dict(original_data.get("scan", {})),
            interactive=InteractiveConfig._from_dict(
                original_data.get("interactive", {})
            ),
            path=config_full_path,
        )

        # Apply overrides
        if overrides:
            logger.info("Applying configuration overrides")
            for override in overrides:
                logger.debug(f"Applying override: {override}")
                config.apply_override(override)
            config.overridden = True

        # Check if config structure changed (new fields added)
        new_data = config.to_dict()
        if not cls._config_equal(original_data, new_data):
            logger.info("Configuration structure changed, updating config file")
            config._update_config(original_data)
            config.updated = True

        if not cls.get_config(raise_if_failed=False):
            global _config_instance
            _config_instance = config
            logger.info("Configuration instance set.")
        else:
            logger.info("The configuration instance already exists; not overwriting.")

        return config

    def apply_override(self, override_str: str):
        """Apply a configuration override using dot notation.

        Args:
            override_str: Override string in format "path.to.key=value"
                         Examples: "app.verbose=true", "scan.limit=200"

        Raises:
            ValueError: If override string is invalid
        """
        if "=" not in override_str:
            logger.error(
                f"Invalid override format: {override_str}. Expected 'key=value'"
            )
            raise ValueError(
                f"Invalid override format: {override_str}. Expected 'key=value'"
            )

        path, value_str = override_str.split("=", 1)
        if not value_str.strip():
            logger.error(f"Invalid override format: {override_str}. Missing value.")
            raise ValueError(f"Invalid override format: {override_str}. Missing value.")
        path = path.strip()

        logger.debug("Override format is valid")

        # Parse value
        value = self._parse_value(value_str)
        logger.debug(f"Parsed override value: {value} (type: {type(value)})")

        # Apply override
        self.set_nested_value(path, value)

    def to_dict(self) -> Dict[str, Any]:
        """Export configuration as dictionary."""
        return {
            "app": self.app._to_dict(),
            "telegram": self.telegram._to_dict(),
            "scan": self.scan._to_dict(),
            "interactive": self.interactive._to_dict(),
        }

    def save(self, path: Optional[Path | str] = None):
        """Save configuration to JSON file."""
        save_path = Path(path) if path else self.path
        logger.info(f"Saving configuration to file: {save_path}")

        if self.overridden:
            logger.error("Configuration has been overridden.")
            raise RuntimeError("Configuration has been overridden.")

        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

        logger.info("Configuration saved successfully.")

    def _parse_value(self, value_str: str) -> Any:
        """Parse string value to appropriate Python type."""
        value_str = value_str.strip()

        if value_str.lower() in ("true", "yes", "1"):
            return True

        if value_str.lower() in ("false", "no", "0"):
            return False

        # None/null
        if value_str.lower() in ("none", "null"):
            return None

        # Number
        try:
            if "." in value_str:
                return float(value_str)
            return int(value_str)
        except ValueError:
            pass

        # try list/dict
        try:
            parsed = json.loads(value_str.replace("'", '"'))
            if isinstance(parsed, (list, dict)):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        # String (remove quotes if present)
        if (value_str.startswith('"') and value_str.endswith('"')) or (
            value_str.startswith("'") and value_str.endswith("'")
        ):
            return value_str[1:-1]

        return value_str

    def set_nested_value(self, path: str, value: Any, bypass_interceptor: bool = False):
        """Set a nested configuration value using dot notation.

        Args:
            path: Dot-separated path to value (e.g., "app.verbose")
            value: Value to set
            bypass_interceptor: Whether to bypass attribute interceptor

        Raises:
            ValueError: If path is invalid
        """
        logger.debug(f"Setting nested configuration value: {path} = {value}")
        parts = path.split(".")

        if len(parts) < 2:
            logger.error(f"Cannot set top-level configuration directly: {path}")
            raise ValueError(f"Cannot set top-level configuration directly: {path}")

        # Navigate to parent object
        obj = self.get_nested_value(
            ".".join(parts[:-1]), bypass_interceptor=bypass_interceptor
        )

        # Set the final value
        attr = parts[-1]
        if not hasattr(obj, attr):
            logger.error(f"Invalid path: {path}. '{attr}' not found.")
            raise ValueError(f"Invalid path: {path}. '{attr}' not found.")

        # Guard against overriding non-data fields
        if callable(getattr(obj, attr)):
            logger.error(f"Cannot override method or callable attribute: {path}")
            raise ValueError(f"Cannot override method or callable attribute: {path}")

        # Type conversion for enums
        if hasattr(obj.__class__, "__dataclass_fields__"):
            field_info = obj.__class__.__dataclass_fields__.get(attr)
            if field_info:
                if field_info.type == ScanMode:
                    value = ScanMode(value)
                elif field_info.type == InteractiveMode:
                    value = InteractiveMode(value)

        interceptor = getattr(obj, "_intercept_set", None)
        if bypass_interceptor or interceptor is None:
            setattr(obj, attr, value)
        else:
            interceptor(attr, value)

    def get_nested_value(self, path: str, bypass_interceptor: bool = False) -> Any:
        """Get a nested configuration value using dot notation.

        Args:
            path: Dot-separated path to value (e.g., "app.verbose")
            bypass_interceptor: Whether to bypass attribute interceptor

        Returns:
            Value at the specified path

        Raises:
            ValueError: If path is invalid
        """
        parts = path.split(".")
        obj = self

        for part in parts:
            if not hasattr(obj, part):
                raise ValueError(f"Invalid path: {path}. '{part}' not found.")
            interceptor = getattr(obj, "_intercept", None)
            if bypass_interceptor or interceptor is None:
                obj = getattr(obj, part)
            else:
                obj = interceptor(part)

        if isinstance(obj, Enum):
            return obj.value

        return obj

    @staticmethod
    def _flatten_dict(
        d: Dict[str, Any], parent_key: str = "", sep: str = "."
    ) -> Dict[str, Any]:
        """Flatten a nested dictionary.

        Args:
            d: Dictionary to flatten
            parent_key: Parent key prefix
            sep: Separator for nested keys

        Returns:
            Flattened dictionary with dot notation keys
        """
        items: List[Tuple[str, Any]] = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(Config._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)

    @staticmethod
    def _config_equal(old: Dict[str, Any], new: Dict[str, Any]) -> bool:
        """Compare two configuration dictionaries for structural equality.

        Returns True if they have the same structure (keys), ignoring values.
        This detects when new fields are added to the config schema.
        """
        # Flatten both dicts
        flat_old = Config._flatten_dict(old)
        flat_new = Config._flatten_dict(new)

        # Compare keys only
        return set(flat_old.keys()) == set(flat_new.keys())

    def _update_config(self, old_data: Dict[str, Any]):
        # Migrate existing config keys to new structure
        logger.info("Migrating existing config keys to new structure")
        if old_data.get("app", {}).get("rapid_save") is not None:
            self.scan.rapid_save = old_data["app"]["rapid_save"]
        if old_data.get("telegram", {}).get("proxies") is not None:
            self.telegram.connection.proxies = old_data["telegram"]["proxies"]
        if old_data.get("telegram", {}).get("direct_connection") is not None:
            self.telegram.connection.direct = old_data["telegram"]["direct_connection"]

        new_data = self.to_dict()

        # Create backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = (
            self.path.parent / f"{self.path.stem}.backup.{timestamp}{self.path.suffix}"
        )
        logger.info(f"Creating backup of old config at: {backup_path}")
        with open(backup_path, "w") as f:
            json.dump(old_data, f, indent=2)
        logger.info(f"Backup created at: {backup_path}")

        logger.info(f"Saving updated config to: {self.path}")
        # Save updated config
        with open(self.path, "w") as f:
            json.dump(new_data, f, indent=2)
        logger.info(f"Updated config saved to: {self.path}")


def get_search_paths() -> List[Path]:
    """Get a list of all configuration search paths."""
    return [Path.cwd(), GLOBAL_CONFIG_PATH.parent]


@overload
def find_config_file(raise_error: Literal[True]) -> Path: ...


@overload
def find_config_file(raise_error: Literal[False]) -> Optional[Path]: ...


def find_config_file(raise_error: bool = False) -> Optional[Path]:  # pragma: no cover
    """Search for configuration file in standard locations."""
    search_paths = get_search_paths()
    config_filenames = ["config.json", "cligram_config.json"]
    logger.info(f"Searching for configuration files in: {search_paths}")

    for search_dir in search_paths:
        for filename in config_filenames:
            candidate = search_dir / filename
            if candidate.exists():
                logger.info(f"Found configuration file: {candidate}")
                return candidate.resolve()
            else:
                logger.debug(f"Configuration file not found at: {candidate}")

    if raise_error:
        logger.error(f"No configuration file found in {search_paths}.")
        raise exceptions.ConfigSearchError(
            "No configuration file found in expected locations."
        )

    logger.warning(f"No configuration file found in {search_paths}.")
    return None
