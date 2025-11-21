""" "Custom Telethon session."""

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, TypeVar, Union, overload

from telethon.sessions import SQLiteSession

from . import Config, exceptions, utils

_TDefault = TypeVar("_TDefault")


class CustomSession(SQLiteSession):
    """Custom Telethon SQLite session with metadata storage and multi-directory search."""

    def __init__(self, session_id: Optional[str] = None, create: bool = False):
        """Initialize custom session.

        Args:
            session_id: Session identifier/name or full path
            create: Whether to create the session file if not found
        """
        config = Config.get_config(raise_if_failed=True)
        session_path: Path = Path(session_id) if session_id else None  # type: ignore

        if session_id is None:
            super().__init__(None)
        elif (
            session_path.suffix == ".session"
            or session_path.is_absolute()
            or os.path.sep in session_id
        ):
            if not session_path.exists() and not create:
                raise exceptions.SessionNotFoundError(
                    f"Session file not found: {session_path}"
                )
            super().__init__(str(session_path))
        else:
            sessions = config.path.get_sessions()
            target = None
            for s in sessions:
                if s.stem == session_id:
                    target = s
                    break

            if target is None:
                if not create:
                    raise exceptions.SessionNotFoundError(
                        f"Session file not found: {session_id}"
                    )

                target = config.path.session_path / f"{session_id}.session"

            super().__init__(str(target))

        self._initialize_metadata_table()

        api_id = config.telegram.api.identifier
        session_api_id = self.get_metadata("api_id")
        if session_api_id is None:
            self.set_metadata("api_id", str(api_id))
        elif session_api_id != api_id:
            raise exceptions.SessionMismatchError(
                "The session was created with a different API ID."
            )

    def _initialize_metadata_table(self):
        """Create metadata table if it doesn't exist."""
        c = self._cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )"""
        )
        c.close()

    def set_metadata(self, key: str, value: Any):
        """Store custom metadata."""
        c = self._cursor()
        c.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            (key, str(value)),
        )
        c.close()

    @overload
    def get_metadata(self, key: str) -> Optional[str]: ...

    @overload
    def get_metadata(self, key: str, default: _TDefault) -> Union[str, _TDefault]: ...

    def get_metadata(self, key: str, default: Optional[Any] = None) -> Optional[Any]:
        """Retrieve custom metadata."""
        c = self._cursor()
        c.execute("SELECT value FROM metadata WHERE key = ?", (key,))
        row = c.fetchone()
        c.close()
        return row[0] if row else default

    def get_all_metadata(self) -> Dict[str, str]:
        """Retrieve all metadata as dictionary."""
        c = self._cursor()
        c.execute("SELECT key, value FROM metadata")
        result = {row[0]: row[1] for row in c.fetchall()}
        c.close()
        return result

    def delete_metadata(self, key: str):
        """Delete metadata entry."""
        c = self._cursor()
        c.execute("DELETE FROM metadata WHERE key = ?", (key,))
        c.close()

    def set_device_info(self, device_info: utils.DeviceInfo):
        """Store device information in metadata."""
        self.set_metadata("device_title", device_info.title)
        self.set_metadata("device_model", device_info.model)

    def get_device_info(self) -> Tuple[Optional[str], Optional[str]]:
        """Retrieve device information from metadata."""
        title = self.get_metadata("device_title", "Unknown Device")
        model = self.get_metadata("device_model", "Unknown Model")
        return title, model
