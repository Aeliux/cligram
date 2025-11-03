import asyncio
import logging
import time
from dataclasses import dataclass
from logging import Logger
from typing import List, Optional, Tuple

from telethon import TelegramClient
from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate

from .proxy_manager import Proxy, ProxyType

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
    logger: Logger,
    timeout: float = 30.0,
    shutdown_event: Optional[asyncio.Event] = None,
) -> List[ProxyTestResult]:
    """Test multiple proxies concurrently and return sorted results."""
    if not proxies:
        return []

    logger.info("[PROXY] Testing proxies...")
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

            status = (
                f"{result.latency:.0f}ms"
                if result.success
                else f"Failed ({result.error})"
            )
            logger.log(
                logging.DEBUG if result.success else logging.WARNING,
                f"[PROXY] {result.proxy.type.value} @ {result.proxy.host}:{result.proxy.port} → {status}",
            )

            if shutdown_event and shutdown_event.is_set():
                logger.warning("[PROXY] Shutdown event triggered, stopping tests")
                break
    except Exception as e:
        logger.error(f"[PROXY] Error during proxy testing: {e}")
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
