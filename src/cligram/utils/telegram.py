from platform import node, release, system
from typing import Optional

from telethon import TelegramClient

from ..config import Config
from ..proxy_manager import Proxy
from ..session import CustomSession


def get_client(config: Config, proxy: Optional[Proxy]) -> TelegramClient:
    """
    Create a Telethon TelegramClient from the given configuration.
    """
    from .. import __version__

    params = {
        "session": CustomSession(config.telegram.session),
        "api_id": config.telegram.api.id,  # API ID from my.telegram.org
        "api_hash": config.telegram.api.hash,  # API hash from my.telegram.org
        "connection_retries": 2,  # Number of attempts before failing
        "device_model": node(),  # Real device model
        "system_version": f"{system()} {release()}",  # Real system details
        "app_version": f"cligram v{__version__}",  # Package version
        "lang_code": "en",  # Language to use for Telegram
        "timeout": 10,  # Timeout in seconds for requests
    }

    if proxy and not proxy.is_direct:
        params.update(proxy.export())

    return TelegramClient(**params)
