import asyncio
import base64
import re
from dataclasses import dataclass
from enum import Enum
from logging import Logger
from typing import List, Optional

import socks
from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate

from .logger import get_logger


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
        self.logger = get_logger()

    proxies: List[Proxy]
    """List of configured proxy connections"""

    current_proxy: Optional[Proxy]
    """Currently selected working proxy"""

    logger: Logger
    """Logger instance for proxy operations"""

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

        try:
            if mtproto_match:
                secret, host, port = mtproto_match.groups()
                return Proxy(
                    ProxyType.MTPROTO, host, int(port), self._decode_secret(secret)
                )
            elif mtproto_tg_match:
                host, port, secret = mtproto_tg_match.groups()
                return Proxy(
                    ProxyType.MTPROTO, host, int(port), self._decode_secret(secret)
                )
            elif socks5_match:
                username, password, host, port = socks5_match.groups()
                return Proxy(
                    ProxyType.SOCKS5,
                    host,
                    int(port),
                    username=username,
                    password=password,
                )
        except Exception as e:
            self.logger.error(f"Failed to parse proxy URL: {e}")
        return None

    async def test_proxies(
        self,
        filter: Optional[ProxyType] = None,
        exclusion: List[Proxy] = [],
        shutdown_event: Optional[asyncio.Event] = None,
        timeout: float = 30.0,
    ) -> Optional[Proxy]:
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
            self.logger.warning("[PROXY] No proxies to test")
            return None

        from .proxy_tester import test_proxies

        results = await test_proxies(
            candidates, self.logger, timeout=timeout, shutdown_event=shutdown_event
        )

        # Return first working proxy
        for result in results:
            if result.success:
                self.current_proxy = result.proxy
                return result.proxy

        return None
