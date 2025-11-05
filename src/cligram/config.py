import base64
import hashlib
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

GLOBAL_CONFIG_DIR = Path.home() / ".cligram"


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

    @property
    def identifier(self) -> str:
        """Get unique identifier for the API credentials."""
        hasher = hashlib.sha256()
        hasher.update(f"{self.id}:{self.hash}".encode("utf-8"))
        digest = hasher.digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8")[:8]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApiConfig":
        return cls(
            id=data.get("id", cls.__dataclass_fields__["id"].default),
            hash=data.get("hash", cls.__dataclass_fields__["hash"].default),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "hash": self.hash}


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
    def from_dict(cls, data: Dict[str, Any]) -> "DelayConfig":
        return cls(
            min=data.get("min", cls.__dataclass_fields__["min"].default),
            max=data.get("max", cls.__dataclass_fields__["max"].default),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"min": self.min, "max": self.max}


@dataclass
class LongDelayConfig(DelayConfig):
    """Configuration for long delay periods."""

    min: float = 30.0
    max: float = 60.0

    chance: float = 0.1
    """Probability (0-1) of taking a long delay instead of normal delay"""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LongDelayConfig":
        return cls(
            min=data.get("min", cls.__dataclass_fields__["min"].default),
            max=data.get("max", cls.__dataclass_fields__["max"].default),
            chance=data.get("chance", cls.__dataclass_fields__["chance"].default),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"min": self.min, "max": self.max, "chance": self.chance}


@dataclass
class DelaysConfig:
    """Delay timing configuration."""

    normal: DelayConfig = field(default_factory=DelayConfig)
    """Normal delay settings"""

    long: LongDelayConfig = field(default_factory=LongDelayConfig)
    """Long break delay settings"""

    def random(self) -> float:
        """
        Generate a random delay based on configured normal and long delays.

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
    def from_dict(cls, data: Dict[str, Any]) -> "DelaysConfig":
        return cls(
            normal=DelayConfig.from_dict(data.get("normal", {})),
            long=LongDelayConfig.from_dict(data.get("long", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"normal": self.normal.to_dict(), "long": self.long.to_dict()}


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
    def from_dict(cls, data: Dict[str, Any]) -> "MessagesConfig":
        return cls(
            source=data.get("source", cls.__dataclass_fields__["source"].default),
            limit=data.get("limit", cls.__dataclass_fields__["limit"].default),
            msg_id=data.get("msg_id", cls.__dataclass_fields__["msg_id"].default),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"source": self.source, "limit": self.limit, "msg_id": self.msg_id}


@dataclass
class ScanConfig:
    """Configuration for scanning behavior and timing."""

    messages: MessagesConfig = field(default_factory=MessagesConfig)
    """Message forwarding settings"""

    mode: ScanMode = ScanMode.FULL
    """Operation mode"""

    targets: List[str] = field(default_factory=list)
    """List of target groups to scan (usernames or URLs)"""

    limit: int = 50
    """Maximum number of messages to scan per group"""

    test: bool = False
    """Test mode without sending messages"""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScanConfig":
        return cls(
            messages=MessagesConfig.from_dict(data.get("messages", {})),
            mode=ScanMode(
                data.get("mode", cls.__dataclass_fields__["mode"].default.value)
            ),
            targets=data.get(
                "targets", cls.__dataclass_fields__["targets"].default_factory()
            ),
            limit=data.get("limit", cls.__dataclass_fields__["limit"].default),
            test=data.get("test", cls.__dataclass_fields__["test"].default),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "messages": self.messages.to_dict(),
            "mode": self.mode.value,
            "targets": self.targets,
            "limit": self.limit,
            "test": self.test,
        }


@dataclass
class TelegramConfig:
    """Telegram client connection settings."""

    api: ApiConfig = field(default_factory=ApiConfig)
    """API credentials from my.telegram.org"""

    session: str = "default"
    """Session file name for persistent authorization"""

    proxies: List[str] = field(default_factory=list)
    """List of proxy URLs to try for connection"""

    direct_connection: bool = True
    """Whether to allow direct connection"""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TelegramConfig":
        return cls(
            api=ApiConfig.from_dict(data.get("api", {})),
            session=data.get("session", cls.__dataclass_fields__["session"].default),
            proxies=data.get(
                "proxies", cls.__dataclass_fields__["proxies"].default_factory()
            ),
            direct_connection=data.get(
                "direct_connection",
                cls.__dataclass_fields__["direct_connection"].default,
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "api": self.api.to_dict(),
            "session": self.session,
            "proxies": self.proxies,
            "direct_connection": self.direct_connection,
        }


@dataclass
class AppConfig:
    """Main application behavior configuration."""

    delays: DelaysConfig = field(default_factory=DelaysConfig)
    """Delay timing configurations"""

    verbose: bool = False
    """Enable debug logging"""

    rapid_save: bool = False
    """Enable rapid state saving to disk"""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        return cls(
            delays=DelaysConfig.from_dict(data.get("delays", {})),
            verbose=data.get("verbose", cls.__dataclass_fields__["verbose"].default),
            rapid_save=data.get(
                "rapid_save", cls.__dataclass_fields__["rapid_save"].default
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "delays": self.delays.to_dict(),
            "verbose": self.verbose,
            "rapid_save": self.rapid_save,
        }


@dataclass
class Config:
    """Application configuration root."""

    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    """Telegram client and connection settings"""

    scan: ScanConfig = field(default_factory=ScanConfig)
    """Scanning behavior and timing settings"""

    app: AppConfig = field(default_factory=AppConfig)
    """Application behavior settings"""

    exclusions: List[str] = field(default_factory=list)
    """List of usernames to exclude from processing"""

    path: Path = field(default=Path("config.json"))
    """Path to the configuration file"""

    updated: bool = False
    """Indicates if the configuration was updated with new fields"""

    @property
    def base_path(self) -> Path:
        """Get base directory of the configuration file."""
        return self.path.parent

    @property
    def data_path(self) -> Path:
        """Get data directory path."""
        return self.base_path / "data"

    @classmethod
    def get_config(cls, raise_if_failed: bool = True) -> "Config":
        """Get application configurations."""
        c = getattr(cls, "_config_instance", None)
        if raise_if_failed:
            if c is None:
                raise RuntimeError("Configuration not loaded. Call from_file() first.")
            if not isinstance(c, cls):
                raise TypeError("Configuration instance is of incorrect type.")

        return c if isinstance(c, cls) else None

    @classmethod
    def from_file(
        cls, config_path: str = "config.json", overrides: Optional[List[str]] = None
    ) -> "Config":
        """Load configuration from JSON file with CLI overrides."""
        config_full_path = Path(config_path).resolve()
        if not config_full_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_full_path, "r") as f:
            original_data = json.load(f)

        # Parse main sections
        config = cls(
            telegram=TelegramConfig.from_dict(original_data.get("telegram", {})),
            scan=ScanConfig.from_dict(original_data.get("scan", {})),
            app=AppConfig.from_dict(original_data.get("app", {})),
            exclusions=original_data.get(
                "exclusions", cls.__dataclass_fields__["exclusions"].default_factory()
            ),
            path=config_full_path,
        )

        # Apply overrides
        if overrides:
            for override in overrides:
                config.apply_override(override)

        # Check if config structure changed (new fields added)
        new_data = config.to_dict()
        if not cls._config_equal(original_data, new_data):
            config._update_config(original_data, new_data)
            config.updated = True

        if not cls.get_config(raise_if_failed=False):
            cls._config_instance = config

        return config

    def apply_override(self, override_str: str):
        """
        Apply a configuration override using dot notation.

        Args:
            override_str: Override string in format "path.to.key=value"
                         Examples: "app.verbose=true", "scan.limit=200"

        Raises:
            ValueError: If override string is invalid
        """
        if "=" not in override_str:
            raise ValueError(
                f"Invalid override format: {override_str}. Expected 'key=value'"
            )

        path, value_str = override_str.split("=", 1)
        path = path.strip()

        # Parse value
        value = self._parse_value(value_str)

        # Apply override
        self._set_nested_value(path, value)

    def to_dict(self) -> Dict[str, Any]:
        """Export configuration as dictionary."""
        return {
            "telegram": self.telegram.to_dict(),
            "scan": self.scan.to_dict(),
            "app": self.app.to_dict(),
        }

    def save(self, path: Optional[str] = None):
        """Save configuration to JSON file."""
        save_path = Path(path) if path else self.path
        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    def _parse_value(self, value_str: str) -> Any:
        """Parse string value to appropriate Python type."""
        # Boolean
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

        # List (JSON array)
        if value_str.startswith("[") and value_str.endswith("]"):
            try:
                return json.loads(value_str)
            except json.JSONDecodeError:
                pass

        # String (remove quotes if present)
        if (value_str.startswith('"') and value_str.endswith('"')) or (
            value_str.startswith("'") and value_str.endswith("'")
        ):
            return value_str[1:-1]

        return value_str

    def _set_nested_value(self, path: str, value: Any):
        """
        Set a nested configuration value using dot notation.

        Args:
            path: Dot-separated path to value (e.g., "app.verbose")
            value: Value to set

        Raises:
            ValueError: If path is invalid
        """
        parts = path.split(".")

        if len(parts) < 2:
            raise ValueError(f"Invalid path: {path}. Must have at least one dot.")

        # Navigate to parent object
        obj = self
        for part in parts[:-1]:
            if not hasattr(obj, part):
                raise ValueError(f"Invalid path: {path}. '{part}' not found.")
            obj = getattr(obj, part)

        # Set the final value
        attr = parts[-1]
        if not hasattr(obj, attr):
            raise ValueError(f"Invalid path: {path}. '{attr}' not found.")

        # Type conversion for enums
        if hasattr(obj.__class__, "__dataclass_fields__"):
            field_info = obj.__class__.__dataclass_fields__.get(attr)
            if field_info and field_info.type == ScanMode:
                value = ScanMode(value)

        setattr(obj, attr, value)

    def get_nested_value(self, path: str) -> Any:
        """
        Get a nested configuration value using dot notation.

        Args:
            path: Dot-separated path to value (e.g., "app.verbose")

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
            obj = getattr(obj, part)

        return obj

    @staticmethod
    def _flatten_dict(
        d: Dict[str, Any], parent_key: str = "", sep: str = "."
    ) -> Dict[str, Any]:
        """
        Flatten a nested dictionary.

        Args:
            d: Dictionary to flatten
            parent_key: Parent key prefix
            sep: Separator for nested keys

        Returns:
            Flattened dictionary with dot notation keys
        """
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(Config._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)

    @staticmethod
    def _config_equal(old: Dict[str, Any], new: Dict[str, Any]) -> bool:
        """
        Compare two configuration dictionaries for structural equality.

        Returns True if they have the same structure (keys), ignoring values.
        This detects when new fields are added to the config schema.
        """
        # Flatten both dicts
        flat_old = Config._flatten_dict(old)
        flat_new = Config._flatten_dict(new)

        # Compare keys only
        return set(flat_old.keys()) == set(flat_new.keys())

    def _update_config(self, old_data: Dict[str, Any], new_data: Dict[str, Any]):
        # Migrate existing config keys to new structure

        # Create backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = (
            self.path.parent / f"{self.path.stem}.backup.{timestamp}{self.path.suffix}"
        )

        with open(backup_path, "w") as f:
            json.dump(old_data, f, indent=2)

        # Save updated config
        with open(self.path, "w") as f:
            json.dump(new_data, f, indent=2)


def get_search_paths() -> List[Path]:
    """Get a list of all configuration search paths."""
    return [Path.cwd(), GLOBAL_CONFIG_DIR]


def find_config_file(raise_error: bool = False) -> Optional[Path]:
    """Search for configuration file in standard locations."""
    search_paths = get_search_paths()
    config_filenames = ["config.json", "cligram_config.json"]

    for search_dir in search_paths:
        for filename in config_filenames:
            candidate = search_dir / filename
            if candidate.exists():
                return candidate.resolve()

    if raise_error:
        raise FileNotFoundError("No configuration file found in standard locations.")

    return None
