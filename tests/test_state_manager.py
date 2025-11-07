import json

import pytest

from cligram.state_manager import GroupInfo, GroupsState, StateManager, UsersState


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
    state.messaged.add(123)
    state.messaged.add(456)
    state.eligible.add("test_user")

    # Save
    state.save(str(state_file))
    assert state_file.exists()

    # Load into new state
    new_state = UsersState()
    new_state.load(str(state_file))

    assert 123 in new_state.messaged
    assert 456 in new_state.messaged
    assert "test_user" in new_state.eligible


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

    # Retrieve again
    retrieved = state.get("group_456")
    assert retrieved.max == 1000
    assert retrieved.min == 500


def test_groups_state_save_load(temp_dir):
    """Test saving and loading groups state."""
    state_file = temp_dir / "groups.json"

    # Create and populate
    state = GroupsState()
    group1 = state.get("group_1")
    group1.max = 2000
    group1.min = 1000

    group2 = state.get("group_2")
    group2.max = 5000

    # Save
    state.save(str(state_file))

    # Load
    new_state = GroupsState()
    new_state.load(str(state_file))

    loaded_group1 = new_state.get("group_1")
    assert loaded_group1.max == 2000
    assert loaded_group1.min == 1000

    loaded_group2 = new_state.get("group_2")
    assert loaded_group2.max == 5000


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
async def test_state_manager_backup(state_dir):
    """Test backup creation."""
    manager = StateManager(str(state_dir))
    manager.users.messaged.add(333)
    await manager.save()

    await manager.backup()

    backup_dir = state_dir / "backup"
    assert backup_dir.exists()

    # Check backup contains timestamp directory
    backups = list(backup_dir.iterdir())
    assert len(backups) > 0
