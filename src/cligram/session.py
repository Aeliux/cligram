import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from telethon.sessions import SQLiteSession

from .config import Config
from .exceptions import SessionMismatchError, SessionNotFoundError


def get_search_paths(config: Optional[Config] = None) -> List[Path]:
    """Get a list of all session search paths."""
    if config is None:
        config = Config.get_config()

    return [
        Path.cwd(),
        Path.cwd() / "sessions",
        config.base_path,
        config.data_path / "sessions",
        Path.home() / ".cligram" / "sessions" / config.telegram.api.identifier,
    ]


class CustomSession(SQLiteSession):
    """
    Custom Telethon SQLite session with metadata storage and multi-directory search.
    """

    def __init__(self, session_id: Optional[str] = None, create: bool = False):
        """
        Initialize custom session.

        Args:
            session_id: Session identifier/name or full path
        """
        if session_id is None:
            super().__init__(None)
            return

        session_path = Path(session_id)

        # If full path provided, use it directly
        if (
            session_path.suffix == ".session"
            or session_path.is_absolute()
            or os.path.sep in session_id
            or "/" in session_id
        ):
            if not session_path.exists() and not create:
                raise SessionNotFoundError(f"Session file not found: {session_path}")
            super().__init__(str(session_path))
        else:
            # Search in provided paths
            search_paths = get_search_paths()
            found_path = None
            for search_dir in search_paths:
                candidate = search_dir / f"{session_id}.session"
                if candidate.exists():
                    found_path = candidate
                    break

            # If not found, create in last path
            if found_path is None:
                if not create:
                    raise SessionNotFoundError(f"Session file not found: {session_id}")

                last_dir = search_paths[-1]
                last_dir.mkdir(parents=True, exist_ok=True)
                found_path = last_dir / f"{session_id}.session"

            super().__init__(str(found_path))
        self._initialize_metadata_table()

        config = Config.get_config()
        api_id = config.telegram.api.identifier
        session_api_id = self.get_metadata("api_id")
        if session_api_id is None:
            self.set_metadata("api_id", str(api_id))
        elif session_api_id != api_id:
            raise SessionMismatchError(
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

    def get_metadata(self, key: str, default: Any = None) -> Optional[str]:
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

    @classmethod
    def list_sessions(cls) -> List[str]:
        """List all session files."""
        sessions: Set[Path] = set()
        for search_dir in get_search_paths():
            sessions.update(search_dir.glob("*.session"))
        return [str(s) for s in sessions]
