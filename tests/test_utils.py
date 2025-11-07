import pytest

from cligram.proxy_manager import Proxy, ProxyType
from cligram.utils.general import validate_proxy


def test_validate_proxy_valid_socks5():
    """Test validation of valid SOCKS5 proxy."""
    proxy = Proxy(
        url="socks5://host:1080",
        type=ProxyType.SOCKS5,
        host="host",
        port=1080,
    )

    assert validate_proxy(proxy) is True


def test_validate_proxy_valid_mtproto():
    """Test validation of valid MTProto proxy."""
    proxy = Proxy(
        url="mtproto://secret@host:443",
        type=ProxyType.MTPROTO,
        host="host",
        port=443,
        secret="secret",
    )

    assert validate_proxy(proxy) is True


def test_validate_proxy_direct():
    """Test validation of direct connection."""
    proxy = Proxy(url="", type=ProxyType.DIRECT, host="", port=0)

    assert validate_proxy(proxy) is True


def test_validate_proxy_invalid_none():
    """Test validation of None proxy."""
    assert validate_proxy(None) is False


def test_validate_proxy_invalid_type():
    """Test validation of invalid type."""
    assert validate_proxy("not a proxy") is False


def test_validate_proxy_missing_host():
    """Test validation of proxy with missing host."""
    proxy = Proxy(
        url="socks5://:1080",
        type=ProxyType.SOCKS5,
        host="",
        port=1080,
    )

    assert validate_proxy(proxy) is False
