import asyncio
import signal
from typing import List

import typer
from rich.console import Console
from rich.status import Status
from rich.style import Style
from rich.table import Table

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
        return f"[{proxy.type.value}] {_get_proxy_host(proxy, use_url=False)}"


def _get_proxy_host(proxy: Proxy, use_url: bool) -> str:
    if proxy.is_direct and not proxy.url:
        return "direct"

    if use_url:
        return proxy.url
    else:
        return f"{proxy.host}:{proxy.port}"


async def run_tests(
    proxy_manager: ProxyManager,
    shutdown_event: asyncio.Event | None = None,
    use_url: bool = False,
    timeout: float = 30.0,
    oneshot: bool = False,
):
    if shutdown_event is None:
        shutdown_event = asyncio.Event()

    def _signal_handler():
        shutdown_event.set()

    signal.signal(signal.SIGINT, lambda s, f: _signal_handler())

    stat = Status("Testing proxies...", spinner="dots")
    stat.start()

    results = []

    results = await proxy_manager.test_proxies(
        shutdown_event=shutdown_event,
        timeout=timeout,
        oneshot=oneshot,
    )

    stat.stop()

    con = Console()
    table = create_console_table(con, use_url)
    table.add_column("Status", justify="center", vertical="middle", max_width=15)

    for i, result in enumerate(results):
        status = f"{result.latency:.0f}ms" if result.success else result.error

        style = Style(
            color=("red" if not result.success else "green" if result.is_good else None)
        )

        table.add_row(
            str(i + 1),
            result.proxy.type.value,
            _get_proxy_host(result.proxy, use_url=use_url),
            status,
            style=style,
        )
    con.print(table)

    return results


def create_console_table(con: Console, use_url: bool):
    table = Table(show_header=True)
    table.add_column("#", justify="center", vertical="middle")
    table.add_column("Type", justify="center", vertical="middle")
    table.add_column("URL" if use_url else "Host", overflow="fold", vertical="middle")
    return table


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
    config: Config = ctx.obj["cligram.init:core"]()
    proxy_manager = ProxyManager()

    for proxy_url in url:
        proxy_manager.add_proxy(proxy_url)

    if not proxy_manager.proxies:
        typer.echo("Failed to add proxy. Please check the URL format.")
        raise typer.Exit(code=1)

    pending: List[Proxy] = []
    if not skip_test:
        shutdown_event = asyncio.Event()
        results: list[ProxyTestResult] = asyncio.run(
            run_tests(proxy_manager, shutdown_event=shutdown_event, use_url=False)
        )

        if shutdown_event.is_set():
            typer.echo("Operation cancelled.")
            raise typer.Exit(code=1)

        pending = [result.proxy for result in results if result.success]
    else:
        pending = proxy_manager.proxies

    c = 0
    for proxy in pending:
        if proxy.url not in config.telegram.connection.proxies:
            config.telegram.connection.proxies.append(proxy.url)
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
    config: Config = ctx.obj["cligram.init:core"]()
    proxy_manager = ProxyManager.from_config(config)

    if not proxy_manager.proxies:
        typer.echo("No proxies configured.")
        raise typer.Exit(code=1)

    typer.echo("Configured Proxies:")
    con = Console()
    table = create_console_table(con, use_url=show_url)
    for i, proxy in enumerate(proxy_manager.proxies):
        table.add_row(
            str(i + 1),
            proxy.type.value,
            _get_proxy_host(proxy, use_url=show_url),
        )
    con.print(table)


@app.command("test")
def test_proxies(
    ctx: typer.Context,
    show_url: bool = typer.Option(
        False, "--show-url", help="Show full proxy URL in the output"
    ),
    timeout: float = typer.Option(30.0, "--timeout", "-t", help="Timeout in seconds"),
    oneshot: bool = typer.Option(
        False, "--oneshot", help="Stop testing after the first successful proxy"
    ),
):
    """
    Test all configured proxies and report their status.
    """
    config: Config = ctx.obj["cligram.init:core"]()
    proxy_manager = ProxyManager.from_config(config)

    asyncio.run(
        run_tests(
            proxy_manager,
            shutdown_event=None,
            use_url=show_url,
            timeout=timeout,
            oneshot=oneshot,
        )
    )


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
    config: Config = ctx.obj["cligram.init:core"]()

    unreachable_proxies: List[str] = []

    if all:
        config.telegram.connection.proxies.clear()
        typer.echo("Removed all proxies from the configuration.")
        config.save()
        raise typer.Exit()

    if unreachable:
        proxy_manager = ProxyManager.from_config(config, exclude_direct=True)
        shutdown_event = asyncio.Event()
        results: list[ProxyTestResult] = asyncio.run(
            run_tests(proxy_manager, shutdown_event=shutdown_event, use_url=False)
        )

        if shutdown_event.is_set():
            typer.echo("Operation cancelled.")
            raise typer.Exit(code=1)

        unreachable_proxies = [
            result.proxy.url for result in results if not result.success
        ]
        typer.echo(f"Found {len(unreachable_proxies)} unreachable proxy(s).")

    c = 0
    target_urls = set(url + unreachable_proxies)
    for proxy_url in target_urls:
        if proxy_url == "direct":
            typer.echo("You must disable direct connection manually in the config.")
            continue
        if proxy_url in config.telegram.connection.proxies:
            config.telegram.connection.proxies.remove(proxy_url)
            c += 1
    if c > 0:
        typer.echo(f"Removed {c} proxy(s) from the configuration.")
        config.save()
    else:
        typer.echo("No matching proxies found.")
        raise typer.Exit(code=1)
