from argparse import ArgumentError

import pytest

from cligram.state_manager import JsonState, StateManager


@pytest.fixture(scope="function", autouse=True)
def clear_registered_states():
    """Clear registered states before and after each test."""
    # Save original registry
    original_registry = StateManager._registered_states.copy()

    # Clear registry for clean test
    StateManager._registered_states.clear()

    yield

    # Restore original registry
    StateManager._registered_states.clear()
    StateManager._registered_states.update(original_registry)


class DummyState(JsonState):
    def __init__(self):
        self._default_data = {"key": "value"}
        self.schema = {"key": str}

        super().__init__()


class DummyState2(JsonState):
    def __init__(self):
        self._default_data = {"count": 0, "items": []}
        self.schema = {"count": int, "items": [str]}
        super().__init__()


class DummyState3(JsonState):
    def __init__(self):
        self._default_data = {"count": 0, "items": []}
        self.schema = {"count": int, "items": set}
        super().__init__()


def test_state_schema_validation(temp_dir):
    """Test schema validation in JsonState."""
    state = DummyState()
    state.data["key"] = "valid_string"
    assert state.changed()

    # Export and validate
    exported = state.export()
    assert '"key"' in exported
    assert '"valid_string"' in exported

    # Load valid data
    new_state = DummyState()
    new_state.load({"key": "another_string"})
    assert new_state.data["key"] == "another_string"

    # Try to load invalid data
    corrupted_state = DummyState()
    with pytest.raises(ValueError):
        corrupted_state.load({"key": 123})  # Invalid type
    assert corrupted_state.data == corrupted_state._default_data


def test_load_invalid_json_file(temp_dir):
    """Test loading invalid JSON file."""
    state_file = temp_dir / "invalid.json"

    # Write invalid JSON
    with open(state_file, "w") as f:
        f.write('{"invalid_json": }')

    state = DummyState()
    with pytest.raises(ValueError):
        with open(state_file, "r") as f:
            content = f.read()
        data = state.parse(content)
        state.load(data)

    # Write invalid structure (not a dict)
    with open(state_file, "w") as f:
        f.write("[1, 2, 3]")

    state2 = DummyState()
    # parse() now accepts lists, but load() should reject them
    with open(state_file, "r") as f:
        content = f.read()
    data = state2.parse(content)
    with pytest.raises(ValueError):
        state2.load(data)


def test_json_state_initialization():
    """Test JsonState initialization."""
    state = DummyState()

    assert state.data == {"key": "value"}
    assert not state.changed()
    assert state.schema == {"key": str}


def test_json_state_change_detection():
    """Test change detection in JsonState."""
    state = DummyState()
    assert not state.changed()

    state.data["key"] = "new_value"
    assert state.changed()

    state.set_changed(False)
    assert not state.changed()

    state.data["key"] = "another_value"
    assert state.changed()


def test_json_state_load_with_unsaved_changes():
    """Test loading state with unsaved changes raises error."""
    state = DummyState()
    state.data["key"] = "modified"

    assert state.changed()

    with pytest.raises(RuntimeError):
        state.load({"key": "new_data"})


def test_json_state_export():
    """Test exporting JsonState."""
    state = DummyState()
    state.data["key"] = "exported_value"

    exported = state.export()
    assert isinstance(exported, str)
    assert "key" in exported
    assert "exported_value" in exported


def test_json_state_sets_to_lists():
    """Test conversion of sets to lists for JSON serialization."""
    state = DummyState3()
    state.data["items"] = {"item1", "item2", "item3"}  # Set instead of list

    exported = state.export()
    # Sets should be converted to lists
    assert isinstance(exported, str)

    # Load it back
    new_state = DummyState2()
    import json

    loaded_data = json.loads(exported)
    new_state.load(loaded_data)
    assert isinstance(new_state.data["items"], list)
    assert set(new_state.data["items"]) == {"item1", "item2", "item3"}


def test_json_state_parse_file_nonexistent():
    """Test parsing empty/non-existent content."""
    # parse() expects content string, not filepath
    with pytest.raises(ValueError):
        JsonState.parse("")  # Empty content should fail


def test_json_state_parse_valid():
    """Test parsing valid JSON content."""
    # Valid dict
    result = JsonState.parse('{"key": "value"}')
    assert result == {"key": "value"}

    # Valid list
    result2 = JsonState.parse("[1, 2, 3]")
    assert result2 == [1, 2, 3]

    # Invalid JSON
    with pytest.raises(ValueError):
        JsonState.parse('{"invalid": }')


def test_state_manager_initialization(state_dir):
    """Test StateManager initialization."""
    StateManager.register("dummy", DummyState)

    manager = StateManager(str(state_dir))

    assert manager.data_dir == state_dir
    assert "dummy" in manager.states
    assert isinstance(manager.states["dummy"], DummyState)


def test_state_manager_register():
    """Test registering states."""
    StateManager.register("test_state", DummyState)

    assert "test_state" in StateManager._registered_states
    assert StateManager._registered_states["test_state"] == DummyState

    # Can't register same name twice
    with pytest.raises(ArgumentError):
        StateManager.register("test_state", DummyState2)

    # Must be a State subclass
    with pytest.raises(TypeError):
        StateManager.register("invalid", str)  # type: ignore

    # Must be a class, not an instance
    with pytest.raises(TypeError):
        StateManager.register("invalid2", DummyState())  # type: ignore


def test_state_manager_get():
    """Test getting states from manager."""
    StateManager.register("dummy", DummyState)
    StateManager.register("another", DummyState2)

    manager = StateManager("test_data")

    # Get without type checking
    state1 = manager.get("dummy")
    assert isinstance(state1, DummyState)

    # Get with type checking
    state2 = manager.get("another", DummyState2)
    assert isinstance(state2, DummyState2)

    # Get with wrong type
    with pytest.raises(TypeError):
        manager.get("dummy", DummyState2)

    # Get non-existent state
    with pytest.raises(KeyError):
        manager.get("nonexistent")


@pytest.mark.asyncio
async def test_state_manager_save(state_dir):
    """Test saving state through manager."""
    StateManager.register("dummy", DummyState)
    StateManager.register("another", DummyState2)

    manager = StateManager(str(state_dir))

    manager.get("dummy").data["key"] = "saved_value"
    manager.get("another").data["count"] = 42

    await manager.save()

    # Verify files exist
    assert (state_dir / "dummy.json").exists()
    assert (state_dir / "another.json").exists()

    # Verify states are marked as unchanged
    assert not manager.get("dummy").changed()
    assert not manager.get("another").changed()


@pytest.mark.asyncio
async def test_state_manager_save_no_changes(state_dir):
    """Test saving when there are no changes."""
    StateManager.register("dummy", DummyState)

    manager = StateManager(str(state_dir))

    # Save without changes
    await manager.save()

    # No files should be created
    assert not (state_dir / "dummy.json").exists()


@pytest.mark.asyncio
async def test_state_manager_load(state_dir):
    """Test loading state through manager."""
    StateManager.register("dummy", DummyState)
    StateManager.register("another", DummyState2)

    # Create initial state
    manager = StateManager(str(state_dir))
    manager.get("dummy").data["key"] = "loaded_value"
    manager.get("another").data["count"] = 99
    await manager.save()

    # Load in new manager
    new_manager = StateManager(str(state_dir))
    await new_manager.load()

    assert new_manager.get("dummy").data["key"] == "loaded_value"
    assert new_manager.get("another").data["count"] == 99


@pytest.mark.asyncio
async def test_state_manager_load_partial(state_dir):
    """Test loading when only some state files exist."""
    StateManager.register("dummy", DummyState)
    StateManager.register("another", DummyState2)

    manager = StateManager(str(state_dir))
    manager.get("dummy").data["key"] = "partial"
    await manager.save()

    # Load in new manager - only dummy exists
    new_manager = StateManager(str(state_dir))
    await new_manager.load()

    assert new_manager.get("dummy").data["key"] == "partial"
    assert new_manager.get("another").data["count"] == 0  # Default value


@pytest.mark.asyncio
async def test_state_manager_backup_restore(state_dir):
    """Test backup creation and restoration."""
    StateManager.register("dummy", DummyState)

    manager = StateManager(str(state_dir))
    manager.get("dummy").data["key"] = "backup_test"
    await manager.save()

    manager.backup()

    backup_dir = state_dir / "backup"
    assert backup_dir.exists()

    # Check backup contains timestamp directory
    backups = list(backup_dir.iterdir())
    assert len(backups) > 0

    # Modify state
    manager.get("dummy").data["key"] = "modified"
    await manager.save()

    # Restore - now synchronous and doesn't load
    manager.restore()

    # State in memory is still modified
    assert manager.get("dummy").data["key"] == "modified"

    # Need to load to see restored data
    await manager.load()
    assert manager.get("dummy").data["key"] == "backup_test"


@pytest.mark.asyncio
async def test_state_manager_backup_no_changes(state_dir):
    """Test backup when there are no changes."""
    StateManager.register("dummy", DummyState)

    manager = StateManager(str(state_dir))

    # Backup without any saves
    manager.backup()

    backup_dir = state_dir / "backup"
    # Backup should be skipped
    assert not backup_dir.exists()


@pytest.mark.asyncio
async def test_state_manager_backup_with_unsaved_changes(state_dir):
    """Test backup with unsaved changes raises error."""
    StateManager.register("dummy", DummyState)

    manager = StateManager(str(state_dir))
    manager.get("dummy", DummyState).data["key"] = "unsaved"
    await manager.save()
    manager.get("dummy", DummyState).data["key"] = "unsaved_change"
    with pytest.raises(RuntimeError):
        manager.backup()


def test_state_manager_restore_specific_timestamp(state_dir):
    """Test restoring specific backup timestamp."""
    StateManager.register("dummy", DummyState)

    manager = StateManager(str(state_dir))

    # No backups exist yet
    with pytest.raises(ValueError):
        manager.restore("20240101_120000")


def test_state_manager_custom_backup_dir(state_dir, tmp_path):
    """Test StateManager with custom backup directory."""
    backup_path = tmp_path / "custom_backup"

    StateManager.register("dummy", DummyState)
    manager = StateManager(str(state_dir), backup_dir=str(backup_path))

    assert manager.backup_dir == backup_path


@pytest.mark.asyncio
async def test_state_manager_atomic_save(state_dir):
    """Test atomic save creates temp file and replaces."""
    StateManager.register("dummy", DummyState)

    manager = StateManager(str(state_dir))
    manager.get("dummy").data["key"] = "atomic_test"

    await manager.save()

    # Verify final file exists and temp file doesn't
    assert (state_dir / "dummy.json").exists()
    assert not (state_dir / "dummy.tmp").exists()


@pytest.mark.asyncio
async def test_state_manager_restore_only_copies_files(state_dir):
    """Test that restore only copies files and doesn't load them."""
    StateManager.register("dummy", DummyState)

    # Create and save initial state
    manager = StateManager(str(state_dir))
    manager.get("dummy").data["key"] = "original"
    await manager.save()
    manager.backup()

    # Modify and save
    manager.get("dummy").data["key"] = "modified"
    await manager.save()

    # Restore files
    manager.restore()

    # In-memory state should still be modified
    assert manager.get("dummy").data["key"] == "modified"
    assert not manager.get("dummy").changed()  # No unsaved changes

    # Create new manager to verify restored files
    new_manager = StateManager(str(state_dir))
    await new_manager.load()
    assert new_manager.get("dummy").data["key"] == "original"


@pytest.mark.asyncio
async def test_state_manager_restore_with_specific_timestamp(state_dir):
    """Test restoring from a specific backup timestamp."""
    StateManager.register("dummy", DummyState)

    manager = StateManager(str(state_dir))

    # Create first backup
    manager.get("dummy").data["key"] = "first"
    await manager.save()
    manager.backup()

    backup_dir = state_dir / "backup"
    first_backup = sorted(backup_dir.iterdir())[0].name

    # Create second backup
    import asyncio

    await asyncio.sleep(1.1)  # Ensure different timestamp
    manager.get("dummy").data["key"] = "second"
    await manager.save()
    manager.backup()

    # Restore first backup
    manager.restore(first_backup)
    await manager.load()

    assert manager.get("dummy").data["key"] == "first"
