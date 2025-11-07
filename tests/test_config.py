import json
from pathlib import Path

import pytest

from cligram.config import (
    GLOBAL_CONFIG_DIR,
    Config,
    InteractiveMode,
    ScanMode,
    get_search_paths,
)


def test_config_from_file(config_file, sample_config_data):
    """Test loading config from file."""
    config = Config.from_file(str(config_file))

    assert config.telegram.api.id == sample_config_data["telegram"]["api"]["id"]
    assert config.telegram.api.hash == sample_config_data["telegram"]["api"]["hash"]
    assert config.scan.mode == ScanMode.FULL
    assert config.scan.limit == 50


def test_config_missing_file():
    """Test error when config file doesn't exist."""
    with pytest.raises(FileNotFoundError):
        Config.from_file("nonexistent.json")


def test_config_override(config_file):
    """Test configuration overrides."""
    config = Config.from_file(
        str(config_file), overrides=["app.verbose=true", "scan.limit=100"]
    )

    assert config.app.verbose is True
    assert config.scan.limit == 100


def test_config_apply_override(config):
    """Test applying individual override."""
    with pytest.raises(ValueError):
        config.apply_override("invalid_override_format")
    with pytest.raises(ValueError):
        config.apply_override("scan.limit=")
    with pytest.raises(ValueError):
        config.apply_override("=100")
    with pytest.raises(ValueError):
        config.apply_override("update=true")
    with pytest.raises(ValueError):
        config.apply_override("app.nonexistent=123")
    with pytest.raises(ValueError):
        config.apply_override("telegram.api.foo=bar")
    with pytest.raises(ValueError):
        config.apply_override("telegram.nonexistent.foo=bar")

    assert config.scan.test is False
    config.apply_override("scan.test=true")
    assert config.scan.test is True
    config.apply_override("scan.test=false")
    assert config.scan.test is False
    config.apply_override("scan.test=yes")
    assert config.scan.test is True
    config.apply_override("scan.test=no")
    assert config.scan.test is False
    config.apply_override("scan.test=1")
    assert config.scan.test is True
    config.apply_override("scan.test=0")
    assert config.scan.test is False
    config.apply_override("scan.test=TrUe")
    assert config.scan.test is True
    config.apply_override("scan.test=null")
    assert config.scan.test is None
    config.apply_override("scan.test=None")
    assert config.scan.test is None
    config.apply_override("scan.test=10")
    assert config.scan.test == 10
    config.apply_override("scan.test=5.5")
    assert config.scan.test == 5.5
    config.apply_override("scan.test=some_string")
    assert config.scan.test == "some_string"
    config.apply_override("scan.test='some_string'")
    assert config.scan.test == "some_string"
    config.apply_override('scan.test="some_string"')
    assert config.scan.test == "some_string"
    config.apply_override("scan.test=[1, 2, 3]")
    assert config.scan.test == [1, 2, 3]
    config.apply_override("scan.test={'key': 'value'}")
    assert isinstance(config.scan.test, dict)
    assert config.scan.test == {"key": "value"}

    assert config.scan.mode == ScanMode.FULL
    config.apply_override("scan.mode=scan")
    assert config.scan.mode == ScanMode.SCAN

    assert config.interactive.mode is InteractiveMode.CLIGRAM
    config.apply_override("interactive.mode=python")
    assert config.interactive.mode is InteractiveMode.PYTHON


def test_config_get_nested_value(config):
    """Test getting nested value via dot notation."""
    with pytest.raises(ValueError):
        config.get_nested_value("app.nonexistent")

    assert config.get_nested_value("telegram.api.id") == config.telegram.api.id
    assert config.get_nested_value("app.verbose") == config.app.verbose
    assert config.get_nested_value("scan.limit") == config.scan.limit
    assert (
        config.get_nested_value("scan.messages.randomize")
        == config.scan.messages.randomize
    )
    assert config.get_nested_value("interactive.mode") == config.interactive.mode
    assert (
        config.get_nested_value("telegram.connection.proxies")
        == config.telegram.connection.proxies
    )


def test_config_invalid_override(config):
    """Test invalid override format."""
    with pytest.raises(ValueError):
        config.apply_override("invalid_format")


def test_config_to_dict(config, sample_config_data):
    """Test config serialization to dict."""
    config_dict = config.to_dict()

    assert (
        config_dict["telegram"]["api"]["id"]
        == sample_config_data["telegram"]["api"]["id"]
    )
    assert "app" in config_dict
    assert "telegram" in config_dict
    assert "scan" in config_dict


def test_get_config(config_file):
    """Test getting global config instance."""
    from cligram import config

    config._config_instance = None  # reset singleton

    # should raise error as no config loaded yet
    with pytest.raises(RuntimeError):
        Config.get_config()

    assert Config.get_config(raise_if_failed=False) is None

    # load config
    loaded_config = Config.from_file(str(config_file))
    assert isinstance(loaded_config, Config)
    assert Config.get_config() is loaded_config

    # set something invalid
    config._config_instance = "invalid"
    with pytest.raises(TypeError):
        Config.get_config()

    assert Config.get_config(raise_if_failed=False) is None

    config._config_instance = None  # reset singleton for other tests


def test_config_save(config, temp_dir):
    """Test saving config to file."""
    save_path = temp_dir / "saved_config.json"
    config.save(str(save_path))

    assert save_path.exists()
    with open(save_path) as f:
        saved_data = json.load(f)

    assert saved_data["telegram"]["api"]["id"] == config.telegram.api.id


def test_delay_config_random(config):
    """Test random delay generation."""
    for _ in range(10):
        delay = config.app.delays.random()
        # Should be within normal or long range
        assert (
            config.app.delays.normal.min <= delay <= config.app.delays.normal.max
            or config.app.delays.long.min <= delay <= config.app.delays.long.max
        )

    # explicitly test normal range
    config.app.delays.long.chance = 0.0
    for _ in range(10):
        delay = config.app.delays.random()
        assert config.app.delays.normal.min <= delay <= config.app.delays.normal.max

    # explicitly test long range
    config.app.delays.long.chance = 1.0
    for _ in range(10):
        delay = config.app.delays.random()
        assert config.app.delays.long.min <= delay <= config.app.delays.long.max


def test_api_identifier(config):
    """Test API identifier generation."""
    identifier = config.telegram.api.identifier
    assert len(identifier) == 8
    assert identifier.isalnum() or "_" in identifier or "-" in identifier


def test_config_scan_randomize_messages(config):
    """Test that messages randomize is correctly inferred from msg_id."""
    assert config.scan.messages.randomize is True
    assert config.scan.messages.msg_id is None

    # now set a dummy id to msg_id
    config.scan.messages.msg_id = 12345
    assert config.scan.messages.randomize is False


def test_ensure_false_update(config):
    assert config.updated is False


def test_trigger_update(sample_config_data, temp_dir):
    del sample_config_data["telegram"]["api"]
    sample_config_data["telegram"]["proxies"] = ["test_proxy"]
    sample_config_data["app"]["rapid_save"] = True
    sample_config_data["telegram"]["direct_connection"] = False
    config_path = temp_dir / "config_update.json"
    with open(config_path, "w") as f:
        json.dump(sample_config_data, f)

    config = Config.from_file(str(config_path))
    assert config.updated is True
    assert config.scan.rapid_save is True
    assert config.telegram.connection.proxies == ["test_proxy"]
    assert config.telegram.connection.direct is False


def test_get_search_paths():
    assert GLOBAL_CONFIG_DIR == Path.home() / ".cligram"
    paths = get_search_paths()
    assert isinstance(paths, list)
    assert Path.cwd() in paths
    assert GLOBAL_CONFIG_DIR in paths
