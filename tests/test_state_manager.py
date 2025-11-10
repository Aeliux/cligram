import logging
from argparse import ArgumentError

import pytest

from cligram.state_manager import GroupsState, JsonState, StateManager, UsersState


# setup function
@pytest.fixture(scope="function", autouse=True)
def setup_logging():
    """Setup logging for tests."""
    from cligram import state_manager

    state_manager.logger = logging.getLogger("cligram.state_manager")
    state_manager.logger.setLevel(logging.FATAL)


class DummyState(JsonState):
    def __init__(self):
        self._default_data = {"key": "value"}
        self.schema = {"key": str}

        super().__init__()


def test_state_schema_validation(temp_dir):
    """Test schema validation in JsonState."""
    state_file = temp_dir / "dummy.json"

    state = DummyState()
    state.data["key"] = "valid_string"
    state.save(str(state_file))

    # Load valid data
    new_state = DummyState()
    new_state.load(str(state_file))
    assert new_state.data["key"] == "valid_string"

    # Corrupt the file with invalid data
    with open(state_file, "w") as f:
        f.write('{"key": 123}')  # Invalid type

    corrupted_state = DummyState()
    with pytest.raises(ValueError):
        corrupted_state.load(str(state_file))
    assert corrupted_state.data == corrupted_state._default_data


def test_load_invalid_state(temp_dir):
    """Test loading invalid state file."""
    state_file = temp_dir / "invalid.json"

    # Write invalid JSON
    with open(state_file, "w") as f:
        f.write('{"invalid_json": }')

    state = DummyState()
    with pytest.raises(ValueError):
        state.load(str(state_file))
    assert state.data == state._default_data

    with open(state_file, "w") as f:
        f.write("[1, 2, 3]")  # Invalid structure

    state2 = DummyState()
    with pytest.raises(ValueError):
        state2.load(str(state_file))


def test_users_state_initialization():
    """Test UsersState initialization."""
    state = UsersState()

    assert isinstance(state.messaged, set)
    assert isinstance(state.eligible, set)
    assert len(state.messaged) == 0
    assert len(state.eligible) == 0


def test_users_state_save_load(temp_dir):
    """Test saving and loading users state."""
    state_file = temp_dir / "users.json"

    # Create and populate state
    state = UsersState()
    assert not state.changed()
    state.messaged.add(123)
    state.messaged.add(456)
    state.eligible.add("test_user")
    assert state.changed()

    # Save
    state.save(str(state_file))
    assert not state.changed()
    assert state_file.exists()

    # Load into new state
    new_state = UsersState()
    new_state.load(str(state_file))
    assert not new_state.changed()

    assert 123 in new_state.messaged
    assert 456 in new_state.messaged
    assert "test_user" in new_state.eligible

    state.messaged.add(789)
    assert state.changed()
    with pytest.raises(RuntimeError):
        state.load(str(state_file))  # Should raise due to unsaved changes


def test_users_state_changed(temp_dir):
    """Test change detection in users state."""
    state = UsersState()

    state_file = temp_dir / "users.json"
    state.save(str(state_file))
    assert not state.changed()  # No changes after save

    state.messaged.add(789)
    assert state.changed()  # Changed after modification


def test_groups_state_initialization():
    """Test GroupsState initialization."""
    state = GroupsState()
    assert len(state.data) == 0


def test_groups_state_get_group():
    """Test getting and creating group info."""
    state = GroupsState()

    group = state.get("group_123")
    assert group.id == "group_123"
    assert group.max is None
    assert group.min is None


def test_groups_state_update_group():
    """Test updating group info."""
    state = GroupsState()

    group = state.get("group_456")
    group.max = 1000
    group.min = 500
    with pytest.raises(AttributeError):
        group.id = "new_id"  # id should be read-only

    # Retrieve again
    retrieved = state.get("group_456")
    assert retrieved.max == 1000
    assert retrieved.min == 500


def test_groups_state_save_load(temp_dir):
    """Test saving and loading groups state."""
    state_file = temp_dir / "groups.json"

    # Create and populate
    state = GroupsState()
    assert not state.changed()
    group1 = state.get("group_1")
    group1.max = 2000
    group1.min = 1000

    group2 = state.get("group_2")
    group2.max = 5000

    assert state.changed()

    # Save
    state.save(str(state_file))

    assert not state.changed()

    # Load
    new_state = GroupsState()
    new_state.load(str(state_file))

    loaded_group1 = new_state.get("group_1")
    assert loaded_group1.max == 2000
    assert loaded_group1.min == 1000

    loaded_group2 = new_state.get("group_2")
    assert loaded_group2.max == 5000
    assert not new_state.changed()

    loaded_group3 = new_state.get("group_3")
    assert not new_state.changed()  # No changes yet
    loaded_group3.max = 3000
    assert new_state.changed()

    with pytest.raises(RuntimeError):
        new_state.load(str(state_file))  # Should raise due to unsaved changes


def test_state_manager_initialization(state_dir):
    """Test StateManager initialization."""
    manager = StateManager(str(state_dir))

    assert manager.data_dir == state_dir
    assert isinstance(manager.users, UsersState)
    assert isinstance(manager.groups, GroupsState)


@pytest.mark.asyncio
async def test_state_manager_save(state_dir):
    """Test saving state through manager."""
    manager = StateManager(str(state_dir))

    manager.users.messaged.add(111)
    manager.users.eligible.add("user1")

    group = manager.groups.get("test_group")
    group.max = 3000

    await manager.save()

    # Verify files exist
    assert (state_dir / "users.json").exists()
    assert (state_dir / "groups.json").exists()


@pytest.mark.asyncio
async def test_state_manager_load(state_dir):
    """Test loading state through manager."""
    # Create initial state
    manager = StateManager(str(state_dir))
    manager.users.messaged.add(222)
    group = manager.groups.get("load_test")
    group.max = 4000
    await manager.save()

    # Load in new manager
    new_manager = StateManager(str(state_dir))
    new_manager.load()

    assert 222 in new_manager.users.messaged
    loaded_group = new_manager.groups.get("load_test")
    assert loaded_group.max == 4000


@pytest.mark.asyncio
async def test_state_manager_load_with_unsaved_changes(state_dir):
    """Test loading state with unsaved changes raises error."""
    manager = StateManager(str(state_dir))
    manager.users.messaged.add(333)

    # Save initial state
    await manager.save()

    # Modify state without saving
    manager.users.eligible.add("unsaved_user")

    with pytest.raises(RuntimeError):
        manager.load()  # Should raise due to unsaved changes


@pytest.mark.asyncio
async def test_state_manager_register_state(state_dir):
    """Test registering a new state in StateManager."""
    manager = StateManager(str(state_dir))

    custom_state = DummyState()
    manager.register("custom", custom_state)

    assert "custom" in manager.states
    assert manager.states["custom"] is custom_state

    custom_state.data["key"] = "new_value"

    await manager.save()

    new_manager = StateManager(str(state_dir))
    new_manager.register("custom", DummyState())
    new_manager.load()
    assert new_manager.states["custom"].data["key"] == "new_value"  # type: ignore

    new_manager.states["custom"].data["key"] = "another_value"  # type: ignore
    await new_manager.save()

    reloaded_manager = StateManager(str(state_dir))
    reloaded_manager.register("custom2", DummyState())
    reloaded_manager.load()
    assert reloaded_manager.states["custom2"].data["key"] == "value"  # type: ignore

    with pytest.raises(ArgumentError):
        manager.register("users", UsersState())  # Already registered

    with pytest.raises(TypeError):
        manager.register("invalid", "not_a_state")  # type: ignore


@pytest.mark.asyncio
async def test_state_manager_backup_restore(state_dir):
    """Test backup creation and restoration."""
    manager = StateManager(str(state_dir))
    manager.users.messaged.add(333)
    await manager.save()

    await manager.backup()

    backup_dir = state_dir / "backup"
    assert backup_dir.exists()

    # Check backup contains timestamp directory
    backups = list(backup_dir.iterdir())
    assert len(backups) > 0

    new_manager = StateManager(state_dir / "restored", backup_dir=backup_dir)
    assert not new_manager.users.messaged  # Empty before restore

    await new_manager.restore()
    await new_manager.save()

    assert 333 in new_manager.users.messaged  # Restored data
    assert not new_manager.users.changed()

    loaded_manager = StateManager(state_dir / "restored")
    assert not loaded_manager.users.messaged

    loaded_manager.load()
    assert 333 in loaded_manager.users.messaged  # Data persists after load
