import json
import tempfile
from pathlib import Path
from typing import Dict

import pytest

from cligram.config import Config


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_config_data() -> Dict:
    """Sample configuration data for testing."""
    return {
        "app": {
            "delays": {
                "normal": {"min": 5.0, "max": 10.0},
                "long": {"min": 20.0, "max": 30.0, "chance": 0.1},
            },
            "verbose": False,
        },
        "telegram": {
            "api": {"id": 12345, "hash": "test_hash_string"},
            "connection": {"direct": True, "proxies": []},
            "startup": {"count_unread_messages": True},
            "session": "test_session",
            "impersonate": False,
        },
        "scan": {
            "messages": {"source": "me", "limit": 20, "msg_id": None},
            "mode": "full",
            "targets": ["test_group1", "test_group2"],
            "limit": 50,
            "test": False,
            "rapid_save": False,
        },
        "interactive": {"mode": "cligram"},
    }


@pytest.fixture
def config_file(temp_dir, sample_config_data):
    """Create a temporary config file."""
    config_path = temp_dir / "config.json"
    with open(config_path, "w") as f:
        json.dump(sample_config_data, f)
    return config_path


@pytest.fixture
def config(config_file):
    """Load a Config instance from temporary file."""
    return Config.from_file(str(config_file))


@pytest.fixture
def state_dir(temp_dir):
    """Create a temporary state directory."""
    state_path = temp_dir / "state"
    state_path.mkdir()
    return state_path
