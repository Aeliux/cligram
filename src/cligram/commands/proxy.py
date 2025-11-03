import asyncio
from typing import List

import typer

from ..config import Config
from ..proxy_manager import Proxy, ProxyManager, ProxyTestResult

app = typer.Typer(
    help="Manage proxy settings and test proxy connectivity",
    add_completion=False,
)


def _get_proxy_title(proxy: Proxy, use_url) -> str:
    if use_url:
        return proxy.url
    else:
        return f"[{proxy.type.value}] {proxy.host}:{proxy.port}"


async def run_tests(
    proxy_manager: ProxyManager, shutdown_event: asyncio.Event, use_url: bool = False
):
    if shutdown_event is None:
        shutdown_event = asyncio.Event()

    results = []

    try:
        results = await proxy_manager.test_proxies(
            shutdown_event=shutdown_event,
        )
        for result in results:
            status = (
                f"{result.latency:.0f}ms"
                if result.success
                else f"Failed ({result.error})"
            )
            typer.echo(f"{_get_proxy_title(result.proxy, use_url=use_url)} → {status}")
    finally:
        shutdown_event.set()

    return results


@app.command("add")
def add_proxy(
    ctx: typer.Context,
    url: List[str] = typer.Argument(help="Proxy URL(s) (mtproto:// or socks5://)"),
    skip_test: bool = typer.Option(
        False, "--skip-test", help="Skip testing the proxy before adding"
    ),
):
    """
    Add a new proxy to the configuration.
    """
    config: Config = ctx.obj["g_load_config"]()
    proxy_manager = ProxyManager()

    for proxy_url in url:
        proxy_manager.add_proxy(proxy_url)

    if not proxy_manager.proxies:
        typer.echo("Failed to add proxy. Please check the URL format.")
        raise typer.Exit(code=1)

    pending: List[Proxy] = []
    if not skip_test:
        results: list[ProxyTestResult] = asyncio.run(
            run_tests(proxy_manager, shutdown_event=None, use_url=False)
        )
        pending = [result.proxy for result in results if result.success]
    else:
        pending = proxy_manager.proxies

    c = 0
    for proxy in pending:
        if proxy.url not in config.telegram.proxies:
            config.telegram.proxies.append(proxy.url)
            c += 1
    if c > 0:
        typer.echo(f"Added {c} new proxy(s) to the configuration.")
        config.save()
    else:
        typer.echo("No new proxies were added to the configuration.")
        raise typer.Exit(code=1)


@app.command("list")
def list_proxies(
    ctx: typer.Context,
    show_url: bool = typer.Option(
        False, "--show-url", help="Show full proxy URL in the output"
    ),
):
    """
    List all configured proxies.
    """
    config: Config = ctx.obj["g_load_config"]()
    proxy_manager = ProxyManager()
    for proxy in config.telegram.proxies:
        proxy_manager.add_proxy(proxy)

    if not proxy_manager.proxies:
        typer.echo("No proxies configured.")
        raise typer.Exit(code=1)

    typer.echo("Configured Proxies:")
    for proxy in proxy_manager.proxies:
        typer.echo(_get_proxy_title(proxy, use_url=show_url))


@app.command("test")
def test_proxies(
    ctx: typer.Context,
    show_url: bool = typer.Option(
        False, "--show-url", help="Show full proxy URL in the output"
    ),
):
    """
    Test all configured proxies and report their status.
    """
    config: Config = ctx.obj["g_load_config"]()
    proxy_manager = ProxyManager()
    for proxy in config.telegram.proxies:
        proxy_manager.add_proxy(proxy)

    asyncio.run(run_tests(proxy_manager, shutdown_event=None, use_url=show_url))


@app.command("remove")
def remove_proxy(
    ctx: typer.Context,
    url: List[str] = typer.Argument(help="Proxy URL(s) (mtproto:// or socks5://)"),
    all: bool = typer.Option(
        False, "--all", "-a", help="Remove all configured proxies"
    ),
    unreachable: bool = typer.Option(
        False, "--unreachable", "-u", help="Remove all unreachable proxies"
    ),
):
    """
    Remove a proxy from the configuration.
    """
    config: Config = ctx.obj["g_load_config"]()
    if all:
        config.telegram.proxies.clear()
        typer.echo("Removed all proxies from the configuration.")
        config.save()
        raise typer.Exit()
    c = 0
    if unreachable:
        proxy_manager = ProxyManager()
        for proxy in config.telegram.proxies:
            proxy_manager.add_proxy(proxy)
        results: list[ProxyTestResult] = asyncio.run(
            run_tests(proxy_manager, shutdown_event=None, use_url=False)
        )
        proxy_url: List[str] = [
            result.proxy.url for result in results if not result.success
        ]
        typer.echo(f"Found {len(proxy_url)} unreachable proxy(s).")
    for proxy_url in url:
        if proxy_url in config.telegram.proxies:
            config.telegram.proxies.remove(proxy_url)
            c += 1
    if c > 0:
        typer.echo(f"Removed {c} proxy(s) from the configuration.")
        config.save()
    else:
        typer.echo("No matching proxies found.")
        raise typer.Exit(code=1)
