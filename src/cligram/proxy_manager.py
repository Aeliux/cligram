import asyncio
import base64
import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from logging import Logger
from typing import List, Optional, Tuple

import socks
from telethon import TelegramClient
from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate


class ProxyType(Enum):
    """
    Type of proxy connection supported by the application.

    Variants:
        MTPROTO: Telegram's native MTProto proxy protocol
        SOCKS5: SOCKS5 proxy protocol with optional authentication
    """

    MTPROTO = "mtproto"
    SOCKS5 = "socks5"


@dataclass
class Proxy:
    """
    Proxy connection configuration.

    Supports both MTProto and SOCKS5 protocols with their respective
    authentication methods. For MTProto, requires secret key; for SOCKS5,
    supports optional username/password authentication.
    """

    url: str
    """Original proxy URL string"""

    type: ProxyType
    """Type of proxy protocol to use"""

    host: str
    """Proxy server hostname or IP address"""

    port: int
    """Proxy server port number"""

    secret: Optional[str] = None
    """MTProto secret key (hex or base64 encoded)"""

    username: Optional[str] = None
    """SOCKS5 authentication username"""

    password: Optional[str] = None
    """SOCKS5 authentication password"""

    def export(self):
        """
        Export proxy configuration for Telethon client.

        Returns:
            dict: Client-compatible proxy configuration parameters
        """
        params = {}

        if self.type == ProxyType.MTPROTO:
            params["connection"] = ConnectionTcpMTProxyRandomizedIntermediate
            params["proxy"] = (self.host, self.port, self.secret)
        elif self.type == ProxyType.SOCKS5:
            params["proxy"] = (
                socks.SOCKS5,
                self.host,
                self.port,
                True,
                self.username,
                self.password,
            )

        return params

    def to_dict(self):
        base = {"type": self.type.value, "host": self.host, "port": self.port}
        if self.type == ProxyType.MTPROTO and self.secret:
            base["secret"] = self.secret
        elif self.type == ProxyType.SOCKS5 and self.username and self.password:
            base["username"] = self.username
            base["password"] = self.password
        return base


class ProxyManager:
    """
    Manages proxy connections and testing.

    Features:
    - Parse multiple proxy URL formats (MTProto, SOCKS5)
    - Connection testing with timeouts
    - Automatic proxy selection
    - Proxy failover support
    """

    def __init__(self):
        self.proxies: List[Proxy] = []
        self.current_proxy: Optional[Proxy] = None

    proxies: List[Proxy]
    """List of configured proxy connections"""

    current_proxy: Optional[Proxy]
    """Currently selected working proxy"""

    def add_proxy(self, proxy_url: str) -> Optional[Proxy]:
        """
        Add new proxy from URL string.

        Args:
            proxy_url: URL string in supported format

        Returns:
            Configured Proxy instance if parsing successful
        """
        proxy = self._parse_proxy_url(proxy_url)
        if proxy and proxy not in self.proxies:
            self.proxies.append(proxy)
        return proxy

    def _decode_secret(self, secret: str) -> str:
        """
        Decode MTProto proxy secret from base64.

        Args:
            secret: Base64 encoded secret string

        Returns:
            Decoded hex string or original if decoding fails
        """
        secret += "=" * ((4 - len(secret) % 4) % 4)
        try:
            return base64.b64decode(secret).hex()
        except:
            return secret

    def _parse_proxy_url(self, proxy_url: str) -> Optional[Proxy]:
        """
        Parse proxy URL into proxy configuration.

        Supports formats:
        - mtproto://<secret>@<host>:<port>
        - tg://proxy?server=<host>&port=<port>&secret=<secret>
        - socks5://[<user>:<pass>@]<host>:<port>

        Args:
            proxy_url: Proxy URL string

        Returns:
            Proxy configuration object or None if parsing fails
        """
        mtproto_match = re.match(r"mtproto://([^@]+)@([^:]+):(\d+)", proxy_url)
        mtproto_tg_match = re.match(
            r"(?:tg|https?://t\.me)/proxy\?server=([^&]+)&port=(\d+)&secret=([^&]+)",
            proxy_url,
        )
        socks5_match = re.match(
            r"socks5://(?:([^:]+):([^@]+)@)?([^:]+):(\d+)", proxy_url
        )

        if mtproto_match:
            secret, host, port = mtproto_match.groups()
            return Proxy(
                type=ProxyType.MTPROTO,
                host=host,
                port=int(port),
                secret=self._decode_secret(secret),
                url=proxy_url,
            )
        elif mtproto_tg_match:
            host, port, secret = mtproto_tg_match.groups()
            return Proxy(
                type=ProxyType.MTPROTO,
                host=host,
                port=int(port),
                secret=self._decode_secret(secret),
                url=proxy_url,
            )
        elif socks5_match:
            username, password, host, port = socks5_match.groups()
            return Proxy(
                type=ProxyType.SOCKS5,
                host=host,
                port=int(port),
                username=username,
                password=password,
                url=proxy_url,
            )
        return None

    async def test_proxies(
        self,
        filter: Optional[ProxyType] = None,
        exclusion: List[Proxy] = [],
        shutdown_event: Optional[asyncio.Event] = None,
        timeout: float = 30.0,
    ) -> List[Proxy]:
        """
        Test proxies to find a working one.

        Args:
            filter: Optional proxy type filter
            exclusion: List of proxies to exclude
            shutdown_event: Event to signal operation shutdown
            timeout: Connection timeout in seconds

        Returns:
            The best working proxy or None if all fail
        """
        candidates = [
            p
            for p in self.proxies
            if (not filter or p.type == filter) and p not in exclusion
        ]

        if not candidates:
            return None

        results = await test_proxies(
            candidates, timeout=timeout, shutdown_event=shutdown_event
        )

        # Return first working proxy
        for result in results:
            if result.success:
                self.current_proxy = result.proxy

        return results


MT_PING_TAG = b"\xee\xee\xee\xee"


@dataclass
class ProxyTestResult:
    """Result of a proxy test including latency and status."""

    proxy: "Proxy"  # Forward reference
    success: bool
    latency: Optional[float] = None
    error: Optional[str] = None

    @property
    def score(self) -> float:
        """Calculate proxy score (lower is better)."""
        if not self.success:
            return float("inf")
        return self.latency or float("inf")


async def ping_mtproto(
    proxy: "Proxy", timeout: float = 30.0
) -> Tuple[bool, Optional[float], Optional[str]]:
    """Test MTProto proxy using actual Telegram connection."""
    start = time.time()

    try:
        # Create temporary client for testing
        client = TelegramClient(
            None,  # Memory session
            1,  # Dummy API ID
            "0" * 32,  # Dummy API hash
            connection=ConnectionTcpMTProxyRandomizedIntermediate,
            proxy=(proxy.host, proxy.port, proxy.secret),
            timeout=timeout,
            auto_reconnect=False,
            connection_retries=1,
            retry_delay=1,
        )

        # Test basic connection
        await asyncio.wait_for(client.connect(), timeout)
        success = True
        error = None

    except asyncio.TimeoutError:
        success = False
        error = "Connection timed out"
    except ConnectionError as e:
        if "Invalid DC" in str(e):
            success = True
            error = None
        else:
            success = False
            error = str(e)
    except Exception as e:
        success = False
        error = str(e)
    finally:
        try:
            await client.disconnect()
        except:
            pass

    latency = (time.time() - start) * 1000 if success else None
    return success, latency, error


async def ping_socks5(
    proxy: "Proxy", timeout: float = 5.0
) -> Tuple[bool, Optional[float], Optional[str]]:
    """Test SOCKS5 proxy with timeout and error reporting."""
    start = time.time()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(proxy.host, proxy.port), timeout
        )
        # Initial greeting
        writer.write(b"\x05\x01\x00")
        await writer.drain()
        resp = await asyncio.wait_for(reader.readexactly(2), timeout)
        if resp != b"\x05\x00":
            return False, None, "SOCKS5 no-auth refused"

        writer.write(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")
        await writer.drain()

        header = await asyncio.wait_for(reader.readexactly(4), timeout)
        if header[0] != 5 or header[1] != 0:
            return False, None, f"SOCKS5 connect failed (REP={header[1]})"

        # Clean up remaining data
        atyp = header[3]
        try:
            if atyp == 1:
                await reader.readexactly(4 + 2)
            elif atyp == 3:
                await reader.readexactly(ord(await reader.readexactly(1)) + 2)
            elif atyp == 4:
                await reader.readexactly(16 + 2)
            else:
                return False, None, f"Unknown address type: {atyp}"
        except Exception:
            pass  # Ignore errors in cleanup

        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass  # Ignore close errors
        return True, (time.time() - start) * 1000, None
    except asyncio.TimeoutError:
        return False, None, "Connection timed out"
    except Exception as e:
        return False, None, str(e)


async def test_proxy(
    proxy: "Proxy", timeout: float = 5.0, shutdown_event: Optional[asyncio.Event] = None
) -> ProxyTestResult:
    """Test a proxy with timeout and shutdown support."""
    if shutdown_event and shutdown_event.is_set():
        return ProxyTestResult(proxy, False, error="Test cancelled")

    test_func = ping_mtproto if proxy.type == ProxyType.MTPROTO else ping_socks5
    success, latency, error = await test_func(proxy, timeout)
    return ProxyTestResult(proxy, success, latency, error)


async def test_proxies(
    proxies: List["Proxy"],
    timeout: float = 30.0,
    shutdown_event: Optional[asyncio.Event] = None,
) -> List[ProxyTestResult]:
    """Test multiple proxies concurrently and return sorted results."""
    if not proxies:
        return []

    # Temporarily suppress Telethon logging
    telethon_logger = logging.getLogger("telethon")
    original_level = telethon_logger.level
    telethon_logger.setLevel(logging.CRITICAL)

    # Create tasks explicitly using asyncio.create_task
    tasks = [
        asyncio.create_task(test_proxy(p, timeout, shutdown_event)) for p in proxies
    ]
    results = []

    try:
        # Use as_completed to get results as they finish
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)

            if shutdown_event and shutdown_event.is_set():
                break
    except Exception:
        pass
    finally:
        # Cancel any remaining tasks
        for task in tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    # Restore original logging level
    telethon_logger.setLevel(original_level)

    # Sort by score (successful proxies first, then by latency)
    results.sort(key=lambda r: r.score)
    return results
