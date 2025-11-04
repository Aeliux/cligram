import asyncio
import copy
import hashlib
import json
import logging
import os
import shutil
from abc import ABC, abstractmethod
from argparse import ArgumentError
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Set

logger = None  # Will be initialized later


class State(ABC):
    """
    Abstract base class for persistent state storage.

    Defines interface for loading, saving, and tracking changes
    to state data with support for validation and atomic operations.
    """

    @abstractmethod
    def load(self, path: str) -> None:
        """
        Load state data from file.

        Args:
            path: Path to state file
        """
        pass

    @abstractmethod
    def save(self, path: str) -> None:
        """
        Save state data to file.

        Args:
            path: Path to state file
        """
        pass

    @abstractmethod
    def changed(self) -> bool:
        """Check if state changed since last save."""
        pass


class JsonState(State):
    """
    JSON-based state persistence implementation.

    Features:
    - Atomic file operations
    - Schema validation
    - Change tracking
    - Data corruption detection
    - Set/list type conversion
    """

    def __init__(self):
        self._default_data: Dict[str, Any] = getattr(self, "_default_data", {})
        self.data: Dict[str, Any] = copy.deepcopy(self._default_data)
        self.schema: Optional[Dict[str, Any]] = None
        self.corrupted: bool = False
        self._should_save: bool = False
        self._last_hash = self.get_hash()

    def _sets_to_lists(self, data: Any) -> Any:
        """
        Convert set objects to lists for JSON serialization.

        Args:
            data: Data structure containing sets

        Returns:
            Data structure with sets converted to lists
        """
        if isinstance(data, dict):
            return {k: self._sets_to_lists(v) for k, v in data.items()}
        elif isinstance(data, set):
            return list(data)
        elif isinstance(data, list):
            return [self._sets_to_lists(item) for item in data]
        return data

    def load(self, path: str) -> None:
        """Load state data from JSON file."""
        if self.changed():
            raise RuntimeError("Cannot load state with unsaved changes")

        data = None

        try:
            data = self._read_json(path)

            if data is None:
                self._should_save = True
                logger.warning(f"[STATE] No data found at {path}")
                return

            if not isinstance(data, dict):
                raise ValueError(
                    f"Invalid data format in {path}: expected dict, got {type(data).__name__}"
                )
        except:
            self.corrupted = True
            raise

        # merge with default data
        data = copy.deepcopy(self._default_data) | data

        if self.schema:
            if not self.verify_structure(data, self.schema):
                self.corrupted = True
                raise ValueError(f"Invalid structure in {path}")
        self.data = data
        self._last_hash = self.get_hash()

    def save(self, path: str) -> None:
        """Save state data to JSON file."""
        if self.corrupted:
            raise RuntimeError("Cannot save corrupted state")

        if self.changed():
            if self.schema:
                if not self.verify_structure(self.data, self.schema):
                    path = f"{path}.corrupted"
                    logger.warning(f"[STATE] Invalid structure, saving to {path}")
            self._atomic_save(path)
            self._should_save = False
            self._last_hash = self.get_hash()

    def changed(self) -> bool:
        """Check if state data has changed since last save."""
        return not self.corrupted and (
            self._should_save
            or self._last_hash is None
            or self.get_hash() != self._last_hash
        )

    def get_hash(self) -> str:
        """Get a hash of the current state data."""
        m = hashlib.sha256()
        json_data = self._sets_to_lists(self.data)
        m.update(json.dumps(json_data, sort_keys=True).encode("utf-8"))
        return m.hexdigest()

    def _read_json(self, path: str) -> Optional[Dict[str, Any]]:
        """Read JSON data from file."""
        try:
            with open(path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    def _atomic_save(self, path: str) -> None:
        """Save state data to JSON file atomically."""
        tmp = f"{path}.tmp"
        try:
            # Convert sets to lists before saving
            json_data = self._sets_to_lists(self.data)
            with open(tmp, "w") as f:
                json.dump(json_data, f, indent=2)
            os.replace(tmp, path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    @classmethod
    def verify_structure(
        cls, data: Any, schema: Dict[str, Any], path: str = ""
    ) -> bool:
        """
        Recursively verify that data matches the provided schema.
        Returns True if valid, False otherwise.
        Logs warnings for mismatches.
        """
        if isinstance(schema, dict):
            if not isinstance(data, dict):
                logger.warning(
                    f"[STATE] Structure mismatch at {path or 'root'}: expected dict, got {type(data).__name__}"
                )
                return False
            for key, subschema in schema.items():
                if key not in data:
                    logger.warning(f"[STATE] Missing key '{key}' at {path or 'root'}")
                    return False
                if not cls.verify_structure(
                    data[key], subschema, path=f"{path}.{key}" if path else key
                ):
                    return False
            return True
        elif isinstance(schema, list):
            if not isinstance(data, list):
                logger.warning(
                    f"[STATE] Structure mismatch at {path or 'root'}: expected list, got {type(data).__name__}"
                )
                return False
            if schema:
                subschema = schema[0]
                for idx, item in enumerate(data):
                    if not cls.verify_structure(item, subschema, path=f"{path}[{idx}]"):
                        return False
            return True
        elif isinstance(schema, type):
            if not isinstance(data, schema):
                logger.warning(
                    f"[STATE] Type mismatch at {path or 'root'}: expected {schema.__name__}, got {type(data).__name__}"
                )
                return False
            return True
        else:
            logger.warning(f"[STATE] Unknown schema type at {path or 'root'}: {schema}")
            return False


class UsersState(JsonState):
    """
    User state tracking implementation.

    Maintains:
    - Set of messaged user IDs
    - Set of eligible usernames
    - Automatic type conversion
    """

    def __init__(self):
        self._default_data = {
            "messaged": set(),
            "eligible": set(),
        }

        super().__init__()

    def load(self, path) -> None:
        """Load user state data from JSON file."""
        super().load(path)

        if not isinstance(self.data["messaged"], set):
            self.data["messaged"] = set(self.data["messaged"])
        if not isinstance(self.data["eligible"], set):
            self.data["eligible"] = set(self.data["eligible"])

        self._last_hash = self.get_hash()

    @property
    def messaged(self) -> Set[int]:
        """Get the set of users that have been messaged."""
        return self.data["messaged"]

    @property
    def eligible(self) -> Set[str]:
        """Get the set of eligible usernames."""
        return self.data["eligible"]


@dataclass
class GroupInfo:
    """
    Represents a chat group's scanning window state.

    The scanning window defines the range of message IDs that have
    been processed, allowing for incremental scanning of large groups.

    On any attribute update (except 'id'), the parent GroupsState's data is updated.
    """

    id: str
    """Group's unique identifier"""

    max: Optional[int] = None
    """Highest message ID scanned"""

    min: Optional[int] = None
    """Lowest message ID scanned"""

    _parent: Optional["GroupsState"] = None
    """Reference to parent GroupsState (not serialized)"""

    def __setattr__(self, name, value):
        if name in ["id", "_parent"]:
            if getattr(self, name, None) is not None:
                raise AttributeError(
                    f"Cannot change '{name}' attribute after initialization"
                )

        super().__setattr__(name, value)
        # Update parent GroupsState's data dict on any change except 'id' and '_parent'
        if (
            name not in ("id", "_parent")
            and hasattr(self, "_parent")
            and self._parent is not None
        ):
            self._parent._update_group_data(self.id, name, value)

    def update(self) -> None:
        """
        Update the group info in the parent GroupsState.

        This method is called to ensure the parent state is updated
        with the current values of this GroupInfo instance.
        """
        if self._parent is not None:
            self._parent.update(self)
        else:
            raise ReferenceError(
                "Cannot update GroupInfo without parent GroupsState reference"
            )


class GroupsState(JsonState):
    """
    Group scanning state implementation.

    Tracks:
    - Message ID windows per group
    - Incremental scanning progress
    - Group metadata

    Keeps GroupInfo and internal data dict in sync on attribute changes.
    """

    def __init__(self):
        super().__init__()

        self._groups: Dict[str, GroupInfo] = {}

    def _update_group_data(self, group_id: str, attr: str, value: Any):
        """Update the internal data dict for a group."""
        if group_id not in self.data:
            self.data[group_id] = {}
        self.data[group_id][attr] = value

    def get(self, group_id: str) -> GroupInfo:
        """Get a group by ID, ensuring live sync with internal data."""
        if group_id in self._groups:
            return self._groups[group_id]

        data = {}
        if group_id in self.data:
            data = self.data[group_id]

        group = GroupInfo(id=group_id, _parent=self, **data)
        self._groups[group_id] = group
        return group

    def update(self, group: GroupInfo) -> None:
        """
        Update or add a group.

        Args:
            group: GroupInfo instance with updated data
        """
        if not isinstance(group, GroupInfo):
            raise TypeError("Expected GroupInfo instance")

        self._groups[group.id] = group
        for key, value in group.__dict__.items():
            if key not in ["id", "_parent"]:
                self._update_group_data(group.id, key, value)


class StateManager:
    """
    Manages persistent application state and handles file-based storage operations.

    Responsible for:
    - Tracking messaged and eligible users
    - Managing group scanning windows
    - Saving/loading state from disk
    - Creating backups of state files
    """

    def __init__(self, data_dir: str, backup_dir: Optional[str] = None):
        """
        Initialize the state manager.

        Args:
            data_dir (str): Path to the data directory storing all state files
        """
        global logger
        logger = logging.getLogger("cligram.state_manager")

        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.backup_dir = (
            Path(backup_dir).resolve() if backup_dir else self.data_dir / "backup"
        )
        self._need_backup = False

        self.lock = asyncio.Lock()

        self.states: Dict[str, State] = {}

        # Initialize core states
        self.users: UsersState = self.register("users", UsersState())
        self.groups: GroupsState = self.register("groups", GroupsState())

    def _get_state_path(self, name: str) -> Path:
        """Get full path for state file."""
        return self.data_dir / f"{name}.json"

    def register(self, name: str, state: State) -> State:
        """Register a new state type."""
        if name in self.states:
            raise ArgumentError(f"State '{name}' is already registered")
        self.states[name] = state
        return state

    def load(self):
        """Load all states from disk."""
        logger.info("[STATE] Loading state...")
        for name, state in self.states.items():
            try:
                if state.changed():
                    logger.warning(
                        f"[STATE] {name} state has unsaved changes, skipping load"
                    )
                    continue
                filepath = self._get_state_path(name)
                state.load(str(filepath))
                logger.info(f"[STATE] Loaded {name} state")
            except Exception as e:
                logger.warning(f"[STATE] Failed to load {name} state: {e}")

    async def save(self):
        """Save changed states to disk."""
        changed = False
        async with self.lock:
            logger.info("[STATE] Saving state...")
            for name, state in self.states.items():
                if state.changed():
                    try:
                        filepath = self._get_state_path(name)
                        state.save(str(filepath))
                        changed = True
                        logger.debug(f"[STATE] Saved {name} state")
                    except Exception as e:
                        logger.error(f"[STATE] Failed to save {name} state: {e}")

        if changed:
            logger.info("[STATE] All states saved")
            self._need_backup = True
        else:
            logger.debug("[STATE] No changes detected")

    async def backup(self):
        """Create backup of all registered states."""
        if not self._need_backup:
            logger.debug("[BACKUP] No changes detected, skipping backup")
            return

        if not self.backup_dir:
            logger.warning("[BACKUP] No backup directory configured")
            return
        if self.backup_dir.is_file():
            logger.error("[BACKUP] Invalid backup directory")
            return

        logger.info("[BACKUP] Creating backup of all states...")

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_dir / timestamp
            backup_path.mkdir(parents=True, exist_ok=True)

            for name, state in self.states.items():
                if state.changed():
                    logger.warning(
                        f"[BACKUP] {name} state has unsaved changes, skipping backup"
                    )
                    continue

                src = self._get_state_path(name)
                if src.exists():
                    dest = backup_path / f"{name}.json"
                    shutil.copy2(src, dest)
                    logger.debug(f"[BACKUP] Backed up {name}")

            logger.info(f"[BACKUP] All states backed up to {backup_path}")
            self._need_backup = False
        except Exception as e:
            logger.error(f"[BACKUP] Failed to create backup: {e}")

    async def restore(self, timestamp: str = None):
        """Restore all states from backup."""
        if not self.backup_dir:
            logger.error("[RESTORE] No backup directory configured")
            return
        if self.backup_dir.is_file():
            logger.error("[RESTORE] Invalid backup directory")
            return
        if not self.backup_dir.exists():
            logger.error("[RESTORE] Backup directory does not exist")
            return

        backup_base = self.backup_dir
        if not timestamp:
            backups = [p for p in backup_base.iterdir() if p.is_dir()]
            if not backups:
                logger.error("[RESTORE] No backups found")
                return
            backup_path = max(backups, key=lambda p: p.name)
        else:
            backup_path = backup_base / timestamp
            if not backup_path.exists():
                logger.error(f"[RESTORE] Backup {timestamp} does not exist")
                return

        logger.info(f"[RESTORE] Restoring states from {backup_path.name}...")

        try:
            restored = 0
            for name, state in self.states.items():
                if state.changed():
                    logger.warning(
                        f"[RESTORE] {name} state has unsaved changes, skipping restore"
                    )
                    continue
                backup = backup_path / f"{name}.json"
                target = self._get_state_path(name)
                if backup.exists():
                    shutil.copy2(backup, target)
                    restored += 1
                    logger.debug(f"[RESTORE] Restored {name}")

            if restored > 0:
                self.load()
                logger.info(
                    f"[RESTORE] Restored {restored} states from {backup_path.name}"
                )
            else:
                logger.warning("[RESTORE] No states restored")
        except Exception as e:
            logger.error(f"[RESTORE] Failed to restore: {e}")

    states: Dict[str, State]
    """Registry of state handlers by name"""

    users: UsersState
    """State handler for user tracking"""

    groups: GroupsState
    """State handler for group tracking"""

    lock: asyncio.Lock
    """Lock for synchronizing state operations"""

    _need_backup: bool
    """Flag indicating if state changes need backup"""
