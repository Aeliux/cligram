import json

import pytest

from cligram.config import Config, ScanMode


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
    config.apply_override("scan.test=true")
    assert config.scan.test is True

    config.apply_override("scan.mode=scan")
    assert config.scan.mode == ScanMode.SCAN


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


def test_api_identifier(config):
    """Test API identifier generation."""
    identifier = config.telegram.api.identifier
    assert len(identifier) == 8
    assert identifier.isalnum() or "_" in identifier or "-" in identifier
