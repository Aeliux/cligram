"""State management module for presistent application data."""

import asyncio
import copy
import hashlib
import logging
import os
import shutil
from abc import ABC, abstractmethod
from argparse import ArgumentError
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, TypeVar, Union, overload

import aiofiles

from . import utils

logger: logging.Logger = logging.getLogger(__name__)


class State(ABC):
    """Abstract base class for state storage.

    Defines interface for loading, exporting, and tracking changes to state data.
    """

    suffix: str = ".state"
    """File suffix for state files"""

    @staticmethod
    def parse(content: str) -> Any:
        """Parse state input contents.

        Subclasses may override this method to implement custom parsing logic.

        The default implementation returns the content as-is.

        Args:
            content: Content of the state file

        Returns:
            Parsed state data, could be passed to load() method
        """
        return content

    @abstractmethod
    def load(self, data: Any) -> None:
        """Load state data.

        Args:
            data: Data to load into state
        """
        pass

    @abstractmethod
    def export(self) -> Any:
        """Export current state data.

        Returns:
            Current state data
        """
        pass

    @abstractmethod
    def changed(self) -> bool:
        """Check if state changed since last reset.

        Returns:
            True if state has changed, False otherwise
        """
        pass

    @abstractmethod
    def set_changed(self, changed: bool) -> None:
        """Set the changed status of the state.

        This method is used internally to mark the state as changed or unchanged.

        Args:
            changed: True to mark state as changed, False to mark as unchanged
        """
        pass


StateT = TypeVar("StateT", bound=State)


class JsonState(State):
    """JSON-based state implementation."""

    data: Dict[str, Any]
    """Current state data"""

    schema: Optional[Dict[str, Any]]
    """Optional schema for data validation"""

    suffix: str = ".json"
    """File suffix for JSON state files"""

    def __init__(self):
        """Initialize JSON state.

        Initializes data with default values and sets up change tracking.
        If a schema is defined, it will be used to validate data structure

        If subclasses define _default_data or schema attributes, they will be used
        instead of empty defaults.
        """
        self._default_data: Dict[str, Any] = getattr(self, "_default_data", {})
        self.data: Dict[str, Any] = copy.deepcopy(self._default_data)
        self.schema: Optional[Dict[str, Any]] = getattr(self, "schema", None)
        self.set_changed(False)

    @staticmethod
    def parse(content: str) -> Dict[str, Any] | list:
        """Parse JSON state contents.

        Args:
            content: Content of the state file

        Returns:
            Parsed state data

        Raises:
            ValueError: If file content is invalid
        """
        try:
            data = utils.json.loads(content)
        except utils.json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON content: {e}") from e

        if not isinstance(data, (dict, list)):
            raise ValueError("Invalid JSON content: expected dict or list at top level")

        return data

    def load(self, data: Optional[Union[Dict[str, Any], str]]) -> None:
        """Load state data from JSON string or dictionary.

        Args:
            data: Data to load into state, either as a dict or JSON string

        Raises:
            RuntimeError: If there are unsaved changes
        """
        if self.changed():
            raise RuntimeError("Cannot load state with unsaved changes")

        if data is None:
            return

        if not isinstance(data, dict):
            raise ValueError(
                f"Invalid data format: expected dict, got {type(data).__name__}"
            )

        # merge with default data
        data = copy.deepcopy(self._default_data) | data

        self.ensure_schema(data)
        self.data = data
        self.set_changed(False)

    def export(self) -> str:
        """Export current state data.

        Returns:
            Current state data
        """
        self.ensure_schema(self.data)
        normalized = JsonState._sets_to_lists(self.data)
        json_data = utils.json.dumps(normalized, sort_keys=True)
        return json_data

    def changed(self) -> bool:
        """Check if state changed since last reset.

        Returns:
            True if state has changed, False otherwise
        """
        return self.get_hash() != self._last_hash

    def set_changed(self, changed: bool) -> None:
        """Set the changed status of the state.

        This method is used internally to mark the state as changed or unchanged.

        Args:
            changed: True to mark state as changed, False to mark as unchanged
        """
        if not changed:
            self._last_hash = self.get_hash()
        else:
            self._last_hash = ""

    def ensure_schema(self, data: Dict[str, Any]) -> None:
        """Ensure current data matches schema.

        Args:
            data: Data to validate

        Raises:
            ValueError: If data does not match schema
        """
        if self.schema:
            if not self.verify_structure(data, self.schema):
                raise ValueError("State data does not match schema")

    def get_hash(self) -> str:
        """Get a hash of the current state data."""
        m = hashlib.sha256()
        json_data = JsonState._sets_to_lists(self.data)
        m.update(utils.json.dumps(json_data, sort_keys=True).encode("utf-8"))
        return m.hexdigest()

    @classmethod
    def verify_structure(
        cls, data: Any, schema: Dict[str, Any], path: str = ""
    ) -> bool:
        """Recursively verify that data matches the provided schema.

        Args:
            data: Data to verify
            schema: Schema definition
            path: Current data path for error messages

        Returns:
            True if data matches schema, False otherwise
        """
        if isinstance(schema, dict):
            if not isinstance(data, dict):
                logger.warning(
                    f"Structure mismatch at {path or 'root'}: expected dict, got {type(data).__name__}"
                )
                return False
            for key, subschema in schema.items():
                if key not in data:
                    logger.warning(f"Missing key '{key}' at {path or 'root'}")
                    return False
                if not cls.verify_structure(
                    data[key], subschema, path=f"{path}.{key}" if path else key
                ):
                    return False
            return True
        elif isinstance(schema, list):
            if not isinstance(data, list):
                logger.warning(
                    f"Structure mismatch at {path or 'root'}: expected list, got {type(data).__name__}"
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
                    f"Type mismatch at {path or 'root'}: expected {schema.__name__}, got {type(data).__name__}"
                )
                return False
            return True
        else:
            logger.warning(f"Unknown schema type at {path or 'root'}: {schema}")
            return False

    @staticmethod
    def _sets_to_lists(data: Any) -> Any:
        """Convert set objects to lists for JSON serialization.

        Args:
            data: Data structure containing sets

        Returns:
            Data structure with sets converted to lists
        """
        if isinstance(data, dict):
            return {k: JsonState._sets_to_lists(v) for k, v in data.items()}
        elif isinstance(data, set):
            return list(data)
        elif isinstance(data, list):
            return [JsonState._sets_to_lists(item) for item in data]
        return data


class StateManager:
    """Manages persistent application state and handles file-based storage operations.

    Provides methods to register state types, load/save states,
    and perform backups/restores of state data.
    """

    _registered_states: Dict[str, type[State]] = {}
    """Class-level registry of state types"""

    def __init__(self, data_dir: str | Path, backup_dir: Optional[str | Path] = None):
        """Initialize the state manager.

        Args:
            data_dir: Directory to store state files
            backup_dir: Directory to store backups (optional)
        """
        self.data_dir = Path(data_dir).resolve()
        """Directory for state files"""

        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.backup_dir = (
            Path(backup_dir).resolve() if backup_dir else self.data_dir / "backup"
        )
        """Directory for backup files"""

        self._need_backup = False
        """Flag indicating if state changes need backup"""

        self.lock = asyncio.Lock()
        """Lock for synchronizing state operations"""

        self.states: Dict[str, State] = {}
        """Registry of state handlers by name"""

        # Initialize all registered states
        for name, state_class in self._registered_states.items():
            self.states[name] = state_class()

    def _get_state_path(self, name: str) -> Path:
        """Get full path for state file."""
        suffix = self.states[name].suffix
        return self.data_dir / f"{name}{suffix}"

    @classmethod
    def register(cls, name: str, state_class: type[State]) -> None:
        """Register a new state type.

        This method does not affect existing StateManager instances.

        Args:
            name: Name of the state
            state_class: State class to register

        Raises:
            TypeError: If state_class is not a State subclass
            ArgumentError: If name is already registered
        """
        if not isinstance(state_class, type) or not issubclass(state_class, State):
            raise TypeError("State must be a subclass of State")

        if name in cls._registered_states:
            raise ArgumentError(None, f"State '{name}' is already registered")

        cls._registered_states[name] = state_class

    @overload
    def get(self, name: str) -> State: ...

    @overload
    def get(self, name: str, expected_type: type[StateT]) -> StateT: ...

    def get(self, name: str, expected_type: Optional[type[State]] = None) -> State:
        """Get registered state by name.

        Args:
            name: Name of the state
            expected_type: Optional expected type of the state

        Returns:
            Registered state instance

        Raises:
            KeyError: If state is not registered
            TypeError: If state type does not match expected_type
        """
        if name not in self.states:
            raise KeyError(f"State '{name}' is not registered")

        state = self.states[name]
        if expected_type and not isinstance(state, expected_type):
            raise TypeError(
                f"State '{name}' is not of expected type {expected_type.__name__}"
            )

        return state

    async def load(self):
        """Load all states from disk."""
        logger.info("Loading state...")
        for name, state in self.states.items():
            filepath = self._get_state_path(name)
            if not filepath.exists():
                continue
            async with aiofiles.open(filepath, "r", encoding="utf-8") as f:
                content = await f.read()
            data = state.parse(content)
            state.load(data)
            logger.info(f"Loaded {name} state")

    async def save(self):
        """Save changed states to disk."""
        changed = False
        async with self.lock:
            logger.info("Saving state...")
            for name, state in self.states.items():
                if not state.changed():
                    continue
                data = state.export()
                filepath = self._get_state_path(name)
                await self._atomic_save(filepath, data)
                state.set_changed(False)
                changed = True
                logger.debug(f"Saved {name} state")

        if changed:
            logger.info("All states saved")
            self._need_backup = True
        else:
            logger.debug("No changes detected")

    async def _atomic_save(self, path: str | Path, data: str):
        """Atomically save state data to disk.

        Args:
            path: Path to state file
            data: State data to save
        """
        filepath = Path(path)
        temp_path = filepath.with_suffix(".tmp")

        async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
            await f.write(data)
        os.replace(temp_path, filepath)

    def backup(self):
        """Create backup of all registered states."""
        if not self._need_backup:
            logger.debug("No changes detected, skipping backup")
            return

        if not self.backup_dir:
            raise ValueError("No backup directory configured")
        if self.backup_dir.is_file():
            raise ValueError("Invalid backup directory")

        logger.info("Creating backup of all states...")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / timestamp
        backup_path.mkdir(parents=True, exist_ok=True)

        for name, state in self.states.items():
            if state.changed():
                raise RuntimeError(f"Cannot backup state with unsaved changes: {name}")

            src = self._get_state_path(name)
            if src.exists():
                dest = backup_path / f"{name}{state.suffix}"
                shutil.copy2(src, dest)
                logger.debug(f"Backed up {name}")

        logger.info(f"All states backed up to {backup_path}")
        self._need_backup = False

    def restore(self, timestamp: Optional[str] = None):
        """Restore all states from backup.

        Restore just copies state files from the backup, overwriting current state files.
        But it does not load them into current StateManager.
        It's highly recommended to create a new StateManager instance after restore.

        Args:
            timestamp: Timestamp of the backup to restore (format: YYYYMMDD_HHMMSS
        """
        if not self.backup_dir:
            raise ValueError("No backup directory configured")
        if self.backup_dir.is_file():
            raise ValueError("Invalid backup directory")
        if not self.backup_dir.exists():
            raise ValueError("Backup directory does not exist")

        backup_base = self.backup_dir
        if not timestamp:
            backups = [p for p in backup_base.iterdir() if p.is_dir()]
            if not backups:
                raise ValueError("No backups found")
            backup_path = max(backups, key=lambda p: p.name)
        else:
            backup_path = backup_base / timestamp
            if not backup_path.exists():
                raise ValueError(f"Backup {timestamp} does not exist")

        logger.info(f"Restoring states from {backup_path.name}...")

        restored = 0
        for name, state in self.states.items():
            if state.changed():
                raise RuntimeError(f"Cannot restore state with unsaved changes: {name}")
            backup = backup_path / f"{name}{state.suffix}"
            target = self._get_state_path(name)
            if backup.exists():
                shutil.copy2(backup, target)
                restored += 1
                logger.debug(f"Restored {name}")

        if restored > 0:
            logger.info(f"Restored {restored} states from {backup_path.name}")
        else:
            logger.warning("No states restored")
