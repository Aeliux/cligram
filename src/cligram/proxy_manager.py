import asyncio
import base64
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Optional, Tuple

import socks
from telethon import TelegramClient, sessions
from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate

if TYPE_CHECKING:
    from . import Config


class ProxyType(Enum):
    """
    Type of proxy connection supported by the application.

    Variants:
        MTPROTO: Telegram's native MTProto proxy protocol
        SOCKS5: SOCKS5 proxy protocol with optional authentication
        DIRECT: Direct connection without proxy
    """

    MTPROTO = "mtproto"
    SOCKS5 = "socks5"
    DIRECT = "direct"


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

    @property
    def is_direct(self) -> bool:
        """Check if the proxy is a direct connection."""
        return self.type == ProxyType.DIRECT

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

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Proxy):
            return False
        if self.type == ProxyType.DIRECT and other.type == ProxyType.DIRECT:
            return True
        return self.url == other.url

    def __hash__(self) -> int:
        if self.type == ProxyType.DIRECT:
            return hash("direct_connection")
        return hash(self.url)


class ProxyManager:
    """
    Manages proxy connections and testing.

    Features:
    - Parse multiple proxy URL formats (MTProto, SOCKS5)
    - Connection testing with timeouts
    - Automatic proxy selection
    - Proxy failover support
    """

    @classmethod
    def from_config(
        cls, config: "Config", exclude_direct: bool = False
    ) -> "ProxyManager":
        """
        Create ProxyManager instance from application config.

        Args:
            config: Application configuration object

        Returns:
            ProxyManager instance
        """
        proxy_manager = cls()
        if config.telegram.connection.direct and not exclude_direct:
            proxy_manager.add_direct_proxy()
        for proxy in config.telegram.connection.proxies:
            proxy_manager.add_proxy(proxy)
        return proxy_manager

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

    def add_direct_proxy(self):
        """
        Add direct connection (no proxy) to the manager.
        """
        direct_proxy = Proxy(
            url="",
            type=ProxyType.DIRECT,
            host="",
            port=0,
        )
        if direct_proxy not in self.proxies:
            self.proxies.append(direct_proxy)

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
        except Exception:
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
        oneshot: bool = False,
    ) -> List["ProxyTestResult"]:

        candidates = [
            p
            for p in self.proxies
            if (not filter or p.type == filter) and p not in exclusion
        ]

        if not candidates:
            return []

        results = await test_proxies(
            candidates, timeout=timeout, shutdown_event=shutdown_event, oneshot=oneshot
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

    @property
    def is_good(self) -> bool:
        """Check if the proxy test was successful."""
        return self.success and (self.latency is not None and self.latency < 1000)


async def ping_mtproto(
    proxy: "Proxy", timeout: float = 30.0
) -> Tuple[bool, Optional[float], Optional[str]]:
    """Test MTProto proxy using actual Telegram connection."""
    return await _test_telegram_connection(
        timeout=timeout,
        connection=ConnectionTcpMTProxyRandomizedIntermediate,
        proxy=(proxy.host, proxy.port, proxy.secret),
    )


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
        return False, None, "timed out"
    except Exception as e:
        return False, None, str(e)


async def ping_direct(
    proxy: "Proxy", timeout: float = 30.0
) -> Tuple[bool, Optional[float], Optional[str]]:
    """Test direct connection to Telegram servers."""
    return await _test_telegram_connection(timeout=timeout, proxy=proxy)


async def _test_telegram_connection(
    timeout: float = 30.0,
    connection=None,
    proxy=None,
) -> Tuple[bool, Optional[float], Optional[str]]:
    """Helper function to test Telegram connection with or without proxy."""
    start = time.time()
    client = None

    try:
        # Create temporary client for testing
        kwargs = {
            "timeout": timeout,
            "auto_reconnect": False,
            "connection_retries": 1,
            "retry_delay": 1,
        }

        if connection:
            kwargs["connection"] = connection
        if not isinstance(proxy, Proxy) or proxy.type != ProxyType.DIRECT:
            kwargs["proxy"] = proxy

        client = TelegramClient(
            None,  # Memory session  # type: ignore
            1,  # Dummy API ID
            "0" * 32,  # Dummy API hash
            **kwargs,
        )

        # Test basic connection
        await asyncio.wait_for(client.connect(), timeout)
        success = True
        error = None

    except asyncio.TimeoutError:
        success = False
        error = "timed out"
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
        if isinstance(client, TelegramClient):
            if (
                isinstance(proxy, Proxy)
                and proxy.type == ProxyType.DIRECT
                and isinstance(client.session, sessions.Session)
            ):
                proxy.host = client.session.server_address
                proxy.port = client.session.port
                proxy.url = f"dc:{client.session.dc_id}"
            dc = client.disconnect()
            if dc is not None:
                await asyncio.shield(dc)

    latency = (time.time() - start) * 1000 if success else None
    return success, latency, error


async def _test_proxy_task(
    proxy: "Proxy",
    timeout: float = 5.0,
) -> ProxyTestResult:
    """Test a proxy with timeout and shutdown support."""
    if proxy.type == ProxyType.MTPROTO:
        test_func = ping_mtproto
    elif proxy.type == ProxyType.SOCKS5:
        test_func = ping_socks5
    elif proxy.type == ProxyType.DIRECT:
        test_func = ping_direct
    else:
        return ProxyTestResult(proxy, False, error="Unknown proxy type")

    try:
        success, latency, error = await test_func(proxy, timeout)
    except asyncio.CancelledError:
        success = False
        latency = None
        error = "Cancelled"
    except Exception as e:
        success = False
        latency = None
        error = str(e)

    return ProxyTestResult(proxy, success, latency, error)


async def test_proxies(
    proxies: List["Proxy"],
    timeout: float = 30.0,
    shutdown_event: Optional[asyncio.Event] = None,
    oneshot: bool = False,
) -> List[ProxyTestResult]:
    """Test multiple proxies concurrently and return sorted results."""
    if not proxies:
        return []

    # Create tasks explicitly using asyncio.create_task
    tasks = [asyncio.create_task(_test_proxy_task(p, timeout)) for p in proxies]
    results = []

    async def wait_for_cancellation():
        final_timeout = (
            timeout + 0.5
        )  # Slightly longer to ensure tasks complete before force stop

        try:
            if shutdown_event:
                await asyncio.wait_for(
                    shutdown_event.wait(),
                    timeout=final_timeout,
                )
            else:
                await asyncio.sleep(final_timeout)
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            pass

    watcher = asyncio.create_task(wait_for_cancellation())

    pending = set(tasks)  # Use a set to track pending tasks
    pending.add(watcher)  # type: ignore

    should_break = False

    try:
        while pending:
            done, pending = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED
            )

            if watcher in done:
                # Shutdown event triggered or timeout elapsed
                break

            for task in done:
                if task is not watcher:
                    result = await task
                    if isinstance(result, ProxyTestResult):
                        results.append(result)
                        if oneshot and result.success:
                            should_break = True
                            break

            if should_break or (len(pending) == 1 and watcher in pending):
                break
    finally:
        # Cancel remaining tasks
        for task in pending:
            if task is not watcher and not task.done():
                task.cancel()
                try:
                    result = await task
                    results.append(result)
                except asyncio.CancelledError:
                    pass
        if not watcher.done():
            watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass

    # Sort by score (successful proxies first, then by latency)
    results.sort(key=lambda r: r.score)
    return results
