from cligram.proxy_manager import Proxy, ProxyManager, ProxyType


def test_proxy_parse_mtproto():
    """Test parsing MTProto proxy URL."""
    manager = ProxyManager()
    proxy = manager.add_proxy("mtproto://secret123@proxy.example.com:443")

    assert proxy is not None
    assert proxy.type == ProxyType.MTPROTO
    assert proxy.host == "proxy.example.com"
    assert proxy.port == 443
    assert proxy.secret is not None


def test_proxy_parse_socks5():
    """Test parsing SOCKS5 proxy URL."""
    manager = ProxyManager()
    proxy = manager.add_proxy("socks5://user:pass@socks.example.com:1080")

    assert proxy is not None
    assert proxy.type == ProxyType.SOCKS5
    assert proxy.host == "socks.example.com"
    assert proxy.port == 1080
    assert proxy.username == "user"
    assert proxy.password == "pass"


def test_proxy_parse_socks5_no_auth():
    """Test parsing SOCKS5 proxy without authentication."""
    manager = ProxyManager()
    proxy = manager.add_proxy("socks5://socks.example.com:1080")

    assert proxy is not None
    assert proxy.type == ProxyType.SOCKS5
    assert proxy.username is None
    assert proxy.password is None


def test_proxy_parse_tg_link():
    manager = ProxyManager()
    proxy = manager.add_proxy(
        "https://t.me/proxy?server=143.20.143.66&port=733&secret=eeNEgYdJvXrFGRMCIMJdCQRueWVrdGFuZXQuY29tZmFyYWthdi5jb212YW4ubmFqdmEuY29tAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    )

    assert proxy is not None
    assert proxy.type == ProxyType.MTPROTO
    assert proxy.host == "143.20.143.66"
    assert proxy.port == 733
    assert proxy.secret is not None


def test_proxy_direct():
    """Test direct connection proxy."""
    manager = ProxyManager()
    manager._add_direct_proxy()

    assert len(manager.proxies) == 1
    assert manager.proxies[0].is_direct


def test_proxy_manager_from_config(config):
    """Test creating proxy manager from config."""
    config.telegram.connection.proxies = [
        "socks5://proxy1.example.com:1080",
        "mtproto://secret@proxy2.example.com:443",
    ]

    manager = ProxyManager.from_config(config)

    assert len(manager.proxies) >= 2  # At least the configured proxies


def test_proxy_export_mtproto():
    """Test exporting MTProto proxy configuration."""
    proxy = Proxy(
        url="mtproto://secret@host:443",
        type=ProxyType.MTPROTO,
        host="host",
        port=443,
        secret="abcd1234",
    )

    export = proxy._export()
    assert "connection" in export
    assert "proxy" in export
    assert export["proxy"][0] == "host"
    assert export["proxy"][1] == 443


def test_proxy_export_socks5():
    """Test exporting SOCKS5 proxy configuration."""
    proxy = Proxy(
        url="socks5://user:pass@host:1080",
        type=ProxyType.SOCKS5,
        host="host",
        port=1080,
        username="user",
        password="pass",
    )

    export = proxy._export()
    assert "proxy" in export
    assert export["proxy"][1] == "host"
    assert export["proxy"][2] == 1080


def test_proxy_equality():
    """Test proxy equality comparison."""
    proxy1 = Proxy(
        url="socks5://host:1080",
        type=ProxyType.SOCKS5,
        host="host",
        port=1080,
    )
    proxy2 = Proxy(
        url="socks5://host:1080",
        type=ProxyType.SOCKS5,
        host="host",
        port=1080,
    )

    assert proxy1 == proxy2


def test_proxy_hash():
    """Test proxy hashing for set operations."""
    proxy1 = Proxy(
        url="socks5://host:1080",
        type=ProxyType.SOCKS5,
        host="host",
        port=1080,
    )
    proxy2 = Proxy(
        url="socks5://host:1080",
        type=ProxyType.SOCKS5,
        host="host",
        port=1080,
    )

    proxy_set = {proxy1, proxy2}
    assert len(proxy_set) == 1  # Should be deduplicated
