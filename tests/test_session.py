import pytest

from cligram.exceptions import SessionNotFoundError
from cligram.session import CustomSession, get_search_paths


def test_session_search_paths():
    """Test session search path generation."""
    paths = get_search_paths()

    assert len(paths) > 0


def test_session_initialization_memory():
    """Test creating memory-only session."""
    session = CustomSession(None)
    assert session is not None
    session.close()


def test_session_not_found():
    """Test error when session file doesn't exist."""
    with pytest.raises(SessionNotFoundError):
        CustomSession("nonexistent_session_file_test_12345", create=False)


def test_session_metadata(temp_dir):
    """Test session metadata storage."""
    session_path = temp_dir / "test_session.session"
    session = CustomSession(str(session_path), create=True)

    # Set metadata
    session.set_metadata("test_key", "test_value")
    session.set_metadata("numeric_key", 12345)

    # Get metadata
    assert session.get_metadata("test_key") == "test_value"
    assert session.get_metadata("numeric_key") == "12345"
    assert session.get_metadata("nonexistent", "default") == "default"

    session.save()
    session.close()


def test_session_get_all_metadata(temp_dir):
    """Test retrieving all metadata."""
    session_path = temp_dir / "test_metadata.session"
    session = CustomSession(str(session_path), create=True)

    session.set_metadata("key1", "value1")
    session.set_metadata("key2", "value2")

    all_meta = session.get_all_metadata()
    assert "key1" in all_meta
    assert "key2" in all_meta
    assert all_meta["key1"] == "value1"

    session.save()
    session.close()


def test_session_delete_metadata(temp_dir):
    """Test deleting metadata."""
    session_path = temp_dir / "test_delete.session"
    session = CustomSession(str(session_path), create=True)

    session.set_metadata("to_delete", "value")
    assert session.get_metadata("to_delete") == "value"

    session.delete_metadata("to_delete")
    assert session.get_metadata("to_delete") is None

    session.save()
    session.close()
